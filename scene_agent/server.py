"""
Scene Agent API Server.

This server exposes HTTP endpoints that allow the frontend, orchestrator, or
another platform service to run the Scene Creator pipeline.
"""

from fastapi import FastAPI
from pydantic import BaseModel

from scene_agent.config.settings import SERVER_HOST, SERVER_PORT
from scene_agent.models.scene_request import RequestManagerContract
from scene_agent.pipeline import ScenePipelineResult, run_scene_creator_pipeline


app = FastAPI(
    title="GotiAI Scene Agent",
    description="API server for running the Scene Creator pipeline.",
    version="0.1.0",
)


class RunScenePipelineRequest(BaseModel):
    """
    Request body for running the full Scene Creator pipeline.
    """

    # Approved contract created by the Request Manager.
    contract: RequestManagerContract


class RunScenePipelineResponse(BaseModel):
    """
    Response returned after the Scene Creator pipeline finishes.
    """

    status: str
    result: ScenePipelineResult


@app.get("/health")
def health_check() -> dict:
    """
    Simple endpoint for checking that the server is running.
    """

    return {"status": "ok"}


@app.post("/scene-agent/run", response_model=RunScenePipelineResponse)
def run_scene_agent(request: RunScenePipelineRequest) -> RunScenePipelineResponse:
    """
    Run the full Scene Creator pipeline from an approved game contract.
    """

    # The pipeline handles analysis, docs retrieval, code generation, and file saving.
    result = run_scene_creator_pipeline(request.contract)

    return RunScenePipelineResponse(
        status="success",
        result=result,
    )


def run_server() -> None:
    """
    Run the API server locally using uvicorn.
    """

    import uvicorn

    uvicorn.run(
        "scene_agent.server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=True,
    )


if __name__ == "__main__":
    run_server()