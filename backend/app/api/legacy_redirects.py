from fastapi import APIRouter
from fastapi.responses import RedirectResponse


router = APIRouter(include_in_schema=False)


@router.get("/ui")
def legacy_console_redirect() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=307)


@router.get("/ui/agentops")
def legacy_agentops_redirect() -> RedirectResponse:
    return RedirectResponse(url="/?technical=runs", status_code=307)


@router.get("/ui/benchmarks")
def legacy_benchmarks_redirect() -> RedirectResponse:
    return RedirectResponse(url="/?technical=evaluation", status_code=307)


@router.get("/ui/backoffice")
def legacy_backoffice_redirect() -> RedirectResponse:
    return RedirectResponse(url="/?technical=approvals", status_code=307)
