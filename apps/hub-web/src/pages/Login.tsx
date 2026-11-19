import { useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { Logo } from "../ui";

export function Login({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api.login(password);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Wrong password." : String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="brand brand-dark">
          <Logo />
          Jigworks
        </div>
        <h1>Hub password</h1>
        <p>The hub is shared by the team behind one password. Engineers running workflows from VS Code never need it.</p>
        <label htmlFor="hub-password">Password</label>
        <input
          id="hub-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          required
        />
        {error && (
          <div className="error-note" role="alert">
            {error}
          </div>
        )}
        <button type="submit" className="btn btn-accent" disabled={busy || !password}>
          {busy ? "Checking…" : "Open the hub"}
        </button>
      </form>
    </div>
  );
}
