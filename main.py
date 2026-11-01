from fastapi import FastAPI

app = FastAPI(title="EM Agent")


@app.get("/api/health")
def health():
    return {"status": "ok"}
