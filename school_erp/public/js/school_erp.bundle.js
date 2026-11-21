// Desk-wide scripts, built by `bench build` into a hashed file so browsers pick up each new
// version at once. Plain /assets/... paths are cached for a year, so a new deploy stayed
// invisible until a hard refresh. Add new desk-wide scripts here, never to app_include_js directly.
import "./school_erp.js";
import "./school_dashboard.js";
import "./verified_documents.js";
