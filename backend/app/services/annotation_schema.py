import math
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models.quality import AnnotationSchema, AnnotationField
from app.repositories.platform import serialize
from app.services.workflow import audit


def schema_detail(db, schema):
    if schema is None:
        return None
    return {
        **serialize(schema),
        "fields": [
            serialize(f)
            for f in db.scalars(
                select(AnnotationField).where(AnnotationField.schema_id == schema.id).order_by(AnnotationField.position)
            )
        ],
    }


def active_schema(db, project_id):
    return db.scalar(
        select(AnnotationSchema)
        .where(AnnotationSchema.project_id == project_id)
        .order_by(AnnotationSchema.version.desc())
        .limit(1)
    )


def create_schema(db, user, project, data):
    version = (
        db.scalar(select(func.max(AnnotationSchema.version)).where(AnnotationSchema.project_id == project.id)) or 0
    ) + 1
    schema = AnnotationSchema(project_id=project.id, version=version, name=data.name, created_by=user.id)
    db.add(schema)
    db.flush()
    for i, field in enumerate(data.fields):
        db.add(AnnotationField(schema_id=schema.id, position=i, **field.model_dump()))
    audit(
        db,
        user,
        "ANNOTATION_SCHEMA_CREATED",
        project_id=project.id,
        payload={"schema_id": schema.id, "version": version},
    )
    db.flush()
    return schema_detail(db, schema)


def validate_values(db, task, values):
    if not task.schema_id:
        if values:
            raise HTTPException(422, "This task uses the legacy annotation form; values must be empty")
        return
    fields = db.scalars(select(AnnotationField).where(AnnotationField.schema_id == task.schema_id)).all()
    unknown = set(values) - {f.key for f in fields}
    errors = [f"Unknown fields: {', '.join(sorted(unknown))}"] if unknown else []
    for field in fields:
        value = values.get(field.key)
        if value is None or value == "" or value == []:
            if field.required:
                errors.append(f"{field.key}: required")
            continue
        kind = field.field_type
        valid = (
            kind == "boolean"
            and isinstance(value, bool)
            or kind == "single_select"
            and isinstance(value, str)
            and value in field.options
            or kind == "multi_select"
            and isinstance(value, list)
            and all(isinstance(x, str) and x in field.options for x in value)
            and len(value) == len(set(value))
            or kind == "integer_rating"
            and type(value) is int
            or kind == "continuous_score"
            and type(value) in (float, int)
            and math.isfinite(value)
            or kind == "text"
            and isinstance(value, str)
            or kind == "json"
            and isinstance(value, (dict, list))
        )
        if not valid:
            errors.append(f"{field.key}: invalid {kind} value")
            continue
        c = field.constraints
        if kind in {"integer_rating", "continuous_score"}:
            if value < c.get("minimum", -math.inf) or value > c.get("maximum", math.inf):
                errors.append(f"{field.key}: outside allowed range")
        if kind == "text" and not c.get("min_length", 0) <= len(value) <= c.get("max_length", 20000):
            errors.append(f"{field.key}: invalid text length")
        if kind == "multi_select" and not c.get("min_items", 0) <= len(value) <= c.get("max_items", 100):
            errors.append(f"{field.key}: invalid number of options")
    if errors:
        raise HTTPException(422, "; ".join(errors))
