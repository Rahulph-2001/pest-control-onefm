// HTTP-level access checks against a running dev site (node >= 18).
// node scripts/http_checks.mjs [http://localhost:8000]
const BASE = process.argv[2] || "http://localhost:8000";
const PASSWORD = "Demo@12345";

async function login(usr, pwd) {
	const r = await fetch(`${BASE}/api/method/login`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ usr, pwd }),
	});
	if (!r.ok) throw new Error(`login ${usr}: ${r.status}`);
	const cookie = r.headers.getSetCookie().map((c) => c.split(";")[0]).join("; ");
	return (path, opts = {}) =>
		fetch(`${BASE}${path}`, {
			...opts,
			headers: { "Content-Type": "application/json", Accept: "application/json", Cookie: cookie, ...(opts.headers || {}) },
			body: opts.body ? JSON.stringify(opts.body) : undefined,
		});
}

const enc = encodeURIComponent;
const results = [];
async function check(label, promise, expectOk) {
	const r = await promise;
	const ok = r.status < 300;
	let body = "";
	try { body = JSON.stringify(await r.json()).slice(0, 140); } catch {}
	const pass = ok === expectOk;
	results.push({ pass, label, status: r.status });
	console.log(`${pass ? "PASS" : "FAIL"}  [${r.status}] ${label}${pass ? "" : "  " + body}`);
	return r;
}

const admin = await login("Administrator", "admin");
const get = async (path) => (await (await admin(path)).json()).message ?? (await (await admin(path)).json()).data;
const list = async (doctype, filters, fields = ["name"]) =>
	(await (await admin(`/api/resource/${enc(doctype)}?filters=${enc(JSON.stringify(filters))}&fields=${enc(JSON.stringify(fields))}&limit_page_length=50`)).json()).data;

const arun = (await list("Employee", { user_id: "field_pc@example.com" }))[0].name;
const arunVisits = (await list("Pest Visit Assignment", { employee: arun, status: "Active" }, ["visit"])).map((a) => a.visit);
const otherVisit = (await list("Pest Service Visit", { name: ["not in", arunVisits.length ? arunVisits : [""]] }))[0].name;
const bilal = (await list("Employee", { user_id: "field2_pc@example.com" }))[0].name;
const evidence = (await list("Pest Employee Verification", { employee: bilal }, ["identity_evidence"]))[0].identity_evidence;
const auditEvent = (await list("Pest Audit Event", { event_category: "Operations" }))[0].name;
const draftVisit = (await list("Pest Service Visit", { status: ["in", ["Draft", "Scheduled"]] }))[0]?.name;

const ops = await login("ops_pc@example.com", PASSWORD);
const hr = await login("hr_pc@example.com", PASSWORD);
const field = await login("field_pc@example.com", PASSWORD);

console.log("\nOperations Manager");
await check("can list visits", ops("/api/resource/Pest%20Service%20Visit"), true);
if (draftVisit) {
	await check("cannot set visit status via REST", ops(`/api/resource/Pest%20Service%20Visit/${enc(draftVisit)}`, { method: "PUT", body: { status: "Completed" } }), false);
	await check("cannot insert an assignment via REST", ops("/api/resource/Pest%20Visit%20Assignment", { method: "POST", body: { visit: draftVisit, staffing_role: "Technician", employee: arun, status: "Active" } }), false);
}
await check("cannot read HR verification record", ops(`/api/resource/Pest%20Employee%20Verification/${enc(bilal)}`), false);
await check("cannot download private evidence file", ops(evidence), false);
await check("cannot decide verification", ops("/api/method/pest_control.verification.decide", { method: "POST", body: { doctype: "Pest Employee Verification", name: bilal, decision: "Revoked", reason: "x" } }), false);
await check("cannot delete audit event", ops(`/api/resource/Pest%20Audit%20Event/${enc(auditEvent)}`, { method: "DELETE" }), false);

console.log("\nHR Verifier");
await check("can read verification record", hr(`/api/resource/Pest%20Employee%20Verification/${enc(bilal)}`), true);
await check("can download evidence file", hr(evidence), true);
await check("cannot set verification_status via REST", hr(`/api/resource/Pest%20Employee%20Verification/${enc(bilal)}`, { method: "PUT", body: { verification_status: "Revoked" } }), false);
await check("cannot allocate staff", hr("/api/method/pest_control.allocation.allocate", { method: "POST", body: { visit: draftVisit || otherVisit, employee: arun, staffing_role: "Technician" } }), false);

console.log("\nField User");
const fieldList = await (await field("/api/resource/Pest%20Service%20Visit?limit_page_length=500")).json();
const visible = (fieldList.data || []).map((v) => v.name);
const onlyOwn = visible.every((v) => arunVisits.includes(v)) && !visible.includes(otherVisit);
results.push({ pass: onlyOwn, label: "visit list shows only own visits" });
console.log(`${onlyOwn ? "PASS" : "FAIL"}  list shows ${visible.length} visit(s), all assigned to this user: ${onlyOwn}`);
await check("cannot open another worker's visit by direct link", field(`/api/resource/Pest%20Service%20Visit/${enc(otherVisit)}`), false);
await check("cannot read verification records", field(`/api/resource/Pest%20Employee%20Verification/${enc(bilal)}`), false);
await check("cannot download another employee's evidence", field(evidence), false);
await check("cannot allocate staff", field("/api/method/pest_control.allocation.allocate", { method: "POST", body: { visit: otherVisit, employee: arun, staffing_role: "Technician" } }), false);
await check("cannot decide verification", field("/api/method/pest_control.verification.decide", { method: "POST", body: { doctype: "Pest Employee Verification", name: bilal, decision: "Verified" } }), false);
await check("cannot read audit log", field(`/api/resource/Pest%20Audit%20Event/${enc(auditEvent)}`), false);

const failed = results.filter((r) => !r.pass).length;
console.log(`\n${results.length - failed}/${results.length} HTTP checks passed`);
process.exit(failed ? 1 : 0);
