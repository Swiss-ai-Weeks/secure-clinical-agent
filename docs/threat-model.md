# Patient360 threat model

See Build Plan §11. This page is the dashboard source for `/threat-model`.

| Threat | Status | Control |
|---|---|---|
| Identity spoofing via prompt or tool args | closed | Identity from run token / session only |
| Forged or replayed tool calls | closed | RFC 9068 run token, session binding |
| Token exfiltration via transcript | closed | Placeholder header when OpenShell is used |
| Direct store access from agent | closed | Egress allowlist; no store credentials in the sandbox |
| Existence oracle | closed | Uniform 404 |
| Pixel exfiltration via tool | closed | Report-only imaging; `/media/sign` is dashboard-only |
| Indirect injection via notes | partial | Presidio + citation output rails |
| Aggregate differencing | partial | k-min, complementary suppression, overlap log |
| Diet orders imply diagnoses | residual | Ward and shift scoped |
