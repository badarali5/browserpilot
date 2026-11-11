import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const user = {
  email: "ada@example.com",
  password: "correct-horse-battery-staple",
  name: "Ada Lovelace",
};

function App() {
  const [view, setView] = useState("home");
  const [profileName, setProfileName] = useState(user.name);
  const [message, setMessage] = useState("");

  function submitRegistration(event) {
    event.preventDefault();
    setView("profile");
  }

  function submitLogin(event) {
    event.preventDefault();
    setView("profile");
  }

  function submitProfile(event) {
    event.preventDefault();
    setMessage("Profile saved");
  }

  if (view === "register") {
    return (
      <main>
        <h1>Create an account</h1>
        <form onSubmit={submitRegistration}>
          <label>Name<input aria-label="Name" required /></label>
          <label>Email<input aria-label="Email" type="email" required /></label>
          <label>Password<input aria-label="Password" type="password" required /></label>
          <button type="submit">Create account</button>
        </form>
        <button className="link" onClick={() => setView("home")}>Back</button>
      </main>
    );
  }

  if (view === "login") {
    return (
      <main>
        <h1>Log in</h1>
        <form onSubmit={submitLogin}>
          <label>Email<input aria-label="Email" type="email" required /></label>
          <label>Password<input aria-label="Password" type="password" required /></label>
          <button type="submit">Log in</button>
        </form>
        <button className="link" onClick={() => setView("reset")}>Reset password</button>
        <button className="link" onClick={() => setView("home")}>Back</button>
      </main>
    );
  }

  if (view === "reset") {
    return (
      <main>
        <h1>Reset your password</h1>
        <form onSubmit={(event) => { event.preventDefault(); setMessage("Reset link sent"); }}>
          <label>Email<input aria-label="Email" type="email" required /></label>
          <button type="submit">Send reset link</button>
        </form>
        {message && <p role="status">{message}</p>}
        <button className="link" onClick={() => setView("login")}>Back to login</button>
      </main>
    );
  }

  if (view === "profile") {
    return (
      <main>
        <h1>Your profile</h1>
        <form onSubmit={submitProfile}>
          <label>Display name<input aria-label="Display name" value={profileName} onChange={(event) => setProfileName(event.target.value)} /></label>
          <button type="submit">Save profile</button>
        </form>
        {message && <p role="status">{message}</p>}
      </main>
    );
  }

  return (
    <main>
      <h1>BrowserPilot Demo</h1>
      <p>Use this controlled application to build a browser-testing baseline.</p>
      <nav aria-label="Account actions">
        <button onClick={() => setView("register")}>Register</button>
        <button onClick={() => setView("login")}>Login</button>
      </nav>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
