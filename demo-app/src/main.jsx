import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const account = { name: "Ada Lovelace", email: "ada@example.com" };

function Brand() {
  return <a className="brand" href="#" aria-label="BrowserPilot Demo"><span className="brand-mark">BP</span><span>BrowserPilot Demo</span></a>;
}

function Shell({ children, view, setView }) {
  return (
    <div className="app">
      <header className="topbar">
        <Brand />
        <nav aria-label="Account actions">
          {view !== "home" && <button className="nav-link" onClick={() => setView("home")}>Home</button>}
          {view === "profile" ? <button className="nav-link" onClick={() => setView("home")}>Logout</button> : null}
        </nav>
      </header>
      <main className="page">{children}</main>
    </div>
  );
}

function Field({ label, type = "text", value, onChange, autoComplete }) {
  const inputProps = value === undefined
    ? {}
    : { value, onChange };
  return <label className="field"><span>{label}</span><input type={type} {...inputProps} onChange={onChange} autoComplete={autoComplete} required /></label>;
}

function App() {
  const [view, setView] = useState("home");
  const [profileName, setProfileName] = useState(account.name);
  const [message, setMessage] = useState("");

  function submit(event, nextView) {
    event.preventDefault();
    setMessage("");
    setView(nextView);
  }

  if (view === "register" || view === "login") {
    const registering = view === "register";
    return (
      <Shell view={view} setView={setView}>
        <section className="auth-layout">
          <div className="auth-art"><span className="eyebrow">Controlled test application</span><h1>{registering ? "Build a test account." : "Welcome back."}</h1><p>{registering ? "Create a sample account and verify the complete registration flow." : "Sign in to continue testing account and profile behavior."}</p></div>
          <div className="auth-panel">
            <form className="auth-card" onSubmit={(event) => submit(event, "profile")}>
              <h2>{registering ? "Create account" : "Log in"}</h2>
              <p>{registering ? "Enter your details to get started." : "Enter your account credentials."}</p>
              {registering && <Field label="Name" autoComplete="name" />}
              <Field label="Email" type="email" autoComplete="email" />
              <Field label="Password" type="password" autoComplete={registering ? "new-password" : "current-password"} />
              <button className="primary" type="submit">{registering ? "Create account" : "Log in"}</button>
              {view === "login" && <button className="link" type="button" onClick={() => setView("reset")}>Reset password</button>}
              <p className="auth-switch">{registering ? "Already registered?" : "New here?"} <button type="button" onClick={() => setView(registering ? "login" : "register")}>{registering ? "Log in" : "Create account"}</button></p>
            </form>
          </div>
        </section>
      </Shell>
    );
  }

  if (view === "reset") {
    return <Shell view={view} setView={setView}><section className="auth-layout"><div className="auth-art"><span className="eyebrow">Password recovery</span><h1>Reset access.</h1></div><div className="auth-panel"><form className="auth-card" onSubmit={(event) => { event.preventDefault(); setMessage("Reset link sent"); }}><h2>Reset password</h2><p>We will send a recovery link to your email.</p><Field label="Email" type="email" /><button className="primary" type="submit">Send reset link</button>{message && <p className="success" role="status">{message}</p>}<button className="link" type="button" onClick={() => setView("login")}>Back to login</button></form></div></section></Shell>;
  }

  if (view === "profile") {
    return <Shell view={view} setView={setView}><section className="profile-layout"><article className="profile-card"><aside><div className="avatar">{profileName[0]}</div><h2>{profileName}</h2><p>{account.email}</p></aside><form className="profile-form" onSubmit={(event) => { event.preventDefault(); setMessage("Profile saved"); }}><h2>Profile details</h2><Field label="Display name" value={profileName} onChange={(event) => setProfileName(event.target.value)} autoComplete="name" /><label className="field"><span>Bio</span><textarea rows="4" /></label><button className="primary" type="submit">Save changes</button>{message && <p className="success" role="status">{message}</p>}</form></article></section></Shell>;
  }

  return (
    <Shell view={view} setView={setView}>
      <section className="hero">
        <span className="eyebrow">Controlled test application</span>
        <h1>Practice browser testing.<br /><span>Ship with confidence.</span></h1>
        <p>A realistic account workflow for validating navigation, forms, validation, profiles, and recovery paths.</p>
        <div className="actions"><button className="primary" onClick={() => setView("register")}>Create account</button><button className="secondary" onClick={() => setView("login")}>Open login</button></div>
        <div className="features"><article><strong>01 · Register</strong><span>Exercise required fields and submission.</span></article><article><strong>02 · Authenticate</strong><span>Validate success and failure paths.</span></article><article><strong>03 · Edit profile</strong><span>Review and save account details.</span></article></div>
      </section>
    </Shell>
  );
}

createRoot(document.getElementById("root")).render(<App />);
