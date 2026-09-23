"""Pure, deterministic format adapters. Unsupported evidence fails explicitly."""

from statistics import mean


def prompt(snapshot):
    payload = snapshot["task"]["input_payload"]
    text = payload.get("prompt") or payload.get("question")
    if isinstance(text, str) and text.strip():
        return text
    for run in snapshot["runs"]:
        for step in run["steps"]:
            if step["step_type"] == "user_message" and step["content"].strip():
                return step["content"]
    raise ValueError("Missing source prompt")


def final_response(run):
    responses = [s["content"] for s in run["steps"] if s["step_type"] == "final_answer" and s["content"].strip()]
    if not responses:
        raise ValueError("Run has no final answer")
    return responses[-1]


def selected_run(snapshot):
    pair = snapshot.get("preference_pair")
    if pair:
        return next(r for r in snapshot["runs"] if r["id"] == pair["chosen_run_id"])
    if len(snapshot["runs"]) != 1:
        raise ValueError("Multiple runs require a reviewer-selected preference pair to identify the chosen response")
    return snapshot["runs"][0]


def reward(snapshot):
    scores = [a["score"] for a in snapshot["annotations"]]
    if not scores:
        raise ValueError("Missing human reward scores")
    return (mean(scores) - 1) / 4


def export_record(snapshot, format):
    if format == "trajectory":
        return {
            "task": snapshot["task"],
            "trajectory": snapshot["runs"],
            "reward": reward(snapshot),
            "metadata": {
                "schema_version": snapshot["schema_version"],
                "project": snapshot["project"],
                "annotations": snapshot["annotations"],
                "reviews": snapshot["reviews"],
                "quality_gate": snapshot["quality_gate"],
            },
        }
    source = prompt(snapshot)
    if format == "dpo":
        pair = snapshot.get("preference_pair")
        if not pair:
            raise ValueError("DPO requires an explicit reviewer-validated preference pair")
        runs = {r["id"]: r for r in snapshot["runs"]}
        chosen = final_response(runs[pair["chosen_run_id"]])
        rejected = final_response(runs[pair["rejected_run_id"]])
        if chosen == rejected:
            raise ValueError("Preference responses must differ")
        return {"prompt": source, "chosen": chosen, "rejected": rejected}
    response = final_response(selected_run(snapshot))
    if format == "sft":
        return {"messages": [{"role": "user", "content": source}, {"role": "assistant", "content": response}]}
    if format == "reward":
        return {"prompt": source, "response": response, "score": reward(snapshot)}
    raise ValueError(f"Unsupported format: {format}")
