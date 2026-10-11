from openenv.core.env_server.http_server import create_app

from ..models import DeskAction, DeskObservation
from .environment import DeskEnvironment

app = create_app(
    DeskEnvironment,
    DeskAction,
    DeskObservation,
    env_name="shiftdesk",
    max_concurrent_envs=16,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
