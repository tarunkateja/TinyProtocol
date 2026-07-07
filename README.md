# TinyProtocol

A gentle, tailored feed & care tracker for newborns — built for real parents at 3am.

TinyProtocol started because tracking feeds for a baby with **GA1 (Glutaric Aciduria
Type 1)** needs more than a generic app can offer: you have to know exactly **how much
breast milk vs. formula vs. metabolic formula** the baby took — including mixed bottles
and estimated intake from direct latching — and watch *natural protein* and *lysine*
against the targets your metabolic team sets. Existing apps track "how many ml, how
long"; they don't understand the numbers that keep a metabolic baby safe.

Every metabolic field is **optional**, so it also works as a plain, fast feed tracker
for any baby.

> This is early, personal software. It is **not medical advice** and must never replace
> guidance from your metabolic team, dietitian, or pediatrician. All seeded nutrition
> values are estimates — confirm every number with your dietitian.

## What it does (v1)

- **Feeds as components**: one feed can mix pumped breast milk (ml) + formula (ml) +
  powder scoops in a single bottle. Direct **latching** is estimated from
  minutes × your ml-per-10-min rate (with an optional weighed override).
- **Nutrition computed automatically**: each food carries natural protein (g) and
  lysine (mg) per 100 ml or per scoop; every feed stores an immutable nutrition
  snapshot. The GA1 metabolic formula is lysine-free and counts as zero.
- **Daily totals vs. targets** (lysine mg/day, natural protein g/day) bucketed in your
  family's timezone.
- **Events**: spit-ups & vomit (severity), fussiness, meds (levocarnitine preset), notes.
- **Doctor summary**: a clean last-12/24/48h rundown — feed totals split by source,
  targets %, meds, spit-ups — shareable as text straight from the app.
- **Two-parent sync**: one family, invite your partner with a code.

## Architecture

```
TinyProtocol/
├── backend/          FastAPI on AWS Lambda (Mangum) + API Gateway + DynamoDB
│   ├── app/
│   │   ├── models/       Pydantic domain models (feed components, foods, events…)
│   │   ├── repo/         single-table DynamoDB layer (keys.py holds every PK/SK)
│   │   ├── services/     nutrition math, timezone windows, summaries, seed data
│   │   └── routers/      auth, babies, foods, feeds, events, timeline, summary
│   ├── tests/            pytest + moto (in-memory DynamoDB)
│   └── template.yaml     AWS SAM stack (dev/prod), us-east-1
└── app/              Expo (React Native, TypeScript) iOS/Android app
    └── src/
        ├── app/          expo-router screens (Today, Totals, Summary, Settings…)
        └── lib/          API client, auth, hooks, theme
```

- **DynamoDB single table**: feeds & events share a per-baby timeline
  (`BABY#id / LOG#<utc-iso>#TYPE#<ulid>`) so one query returns the interleaved
  chronological log. A GSI resolves items by id. ~$0/month at family scale.
- **Auth**: email+password (bcrypt) with 90-day JWTs; every query is scoped to the
  family in the token.

## Getting started

### Backend

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # moto-backed, no AWS needed
uvicorn app.main:app --reload   # local dev (uses DynamoDB Local or a dev table)
```

Deploy (needs AWS credentials + SAM CLI):

```bash
sam build
sam deploy --config-env dev --parameter-overrides "Stage=dev JwtSecret=<32+ char secret>"
```

### App (Expo)

```bash
cd app
npm install
npm start          # scan the QR code with your iPhone camera (Expo Go)
```

The app points at the deployed dev API by default; override with
`EXPO_PUBLIC_API_URL=http://<your-mac-ip>:8000 npm start` for a local backend.

## Roadmap

Weight tracking with per-kg auto targets · sick-day / emergency-regimen mode ·
pumping & freezer stash · diapers & sleep · offline-first logging · TestFlight →
App Store for other families.

## License

MIT — see [LICENSE](LICENSE). Built with hope that it helps other families too. 💛
