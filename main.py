from applications.review_ui import create_review_surface_app
from mediator.mediator import Mediator


def create_app():
    return create_review_surface_app(Mediator([]))


app = create_app()
