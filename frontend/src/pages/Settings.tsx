import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { api, send } from "../api";
import type { User } from "../types";
import { useApp } from "../context";
import {
  PageHeading,
  Button,
  Input,
  Select,
  Modal,
  Badge,
  ErrorState,
  Skeleton,
} from "../components/ui";
export default function Settings() {
  const { user, notify } = useApp(),
    qc = useQueryClient(),
    [open, setOpen] = useState(false),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [name, setName] = useState(""),
    [role, setRole] = useState("ANNOTATOR");
  const q = useQuery({
    queryKey: ["users"],
    queryFn: () => api<User[]>("/users"),
  });
  const create = useMutation({
    mutationFn: () =>
      send("/users", { email, password, full_name: name, role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setOpen(false);
      setPassword("");
      notify("Team member created");
    },
  });
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE"
        title="Settings"
        description="Manage your profile and the people behind your feedback loop."
      />
      <section className="panel">
        <div className="section-heading">
          <h2>Your profile</h2>
          <Badge status={user.role} />
        </div>
        <div className="padded">
          <h3>{user.full_name}</h3>
          <p className="muted">{user.email}</p>
        </div>
      </section>
      <section className="panel settings-team">
        <div className="section-heading">
          <div>
            <h2>Workspace members</h2>
            <p>Roles define project, annotation, and review permissions</p>
          </div>
          {user.role === "ADMIN" && (
            <Button onClick={() => setOpen(true)}>
              <Plus size={15} />
              Add member
            </Button>
          )}
        </div>
        {q.isPending ? (
          <Skeleton />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : (
          q.data.map((u) => (
            <div className="member-row" key={u.id}>
              <span className="avatar">{u.full_name.slice(0, 1)}</span>
              <div>
                <strong>{u.full_name}</strong>
                <p>{u.email}</p>
              </div>
              <Badge status={u.role} />
            </div>
          ))
        )}
      </section>
      {open && (
        <Modal title="Add workspace member" onClose={() => setOpen(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label>
              Full name
              <Input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Email
              <Input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Password
              <Input
                required
                type="password"
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              Role
              <Select value={role} onChange={(e) => setRole(e.target.value)}>
                <option>ANNOTATOR</option>
                <option>REVIEWER</option>
                <option>ADMIN</option>
              </Select>
            </label>
            {create.error && <ErrorState error={create.error} />}
            <Button disabled={create.isPending}>Create member</Button>
          </form>
        </Modal>
      )}
    </>
  );
}
