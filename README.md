# Cerebro engine

Run engine API:
```
(INNGEST_DEV=1 uvicorn server:app --reload)
```


Run `inngest` orchestrator:

```
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest --no-discovery
```

