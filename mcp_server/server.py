from fastapi import FastAPI

app = FastAPI(title="OpsPilot MCP Server")

@app.get("/health")
def health_check():
    return {"status": "ok", "layer": "mcp-server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
