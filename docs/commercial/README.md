# Commercial docs (NEXT-07)

| Document | Purpose |
|----------|---------|
| [cost-model.md](./cost-model.md) | Cost inventory, meters, formula, tier discovery |
| [pricing-decision.md](./pricing-decision.md) | **Paddle** chosen; tier prices; STOP before payments |

Machine-readable:

- `config/commercial_cost_catalog.json`
- `config/plan_catalog.json` (regenerate: `python -m core.commercial.pricing`)

Aktueller Implementierungsstand PR144: [Offline-Lizenzen und Paddle-Betrieb](OFFLINE_LICENSE_AND_PADDLE_RUNBOOK.md). Alte Preis-/Kostenentscheidungen sind historische Annahmen, keine aktivierten Angebote. Öffentliche Buildkonfiguration: `config/commercial_release.json`; Verkauf standardmäßig deaktiviert.
