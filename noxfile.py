# noxfile.py
from nox_poetry import Session, session

PY_VERSIONS = ["3.11"]  # add more if you test multiple versions

@session(python=PY_VERSIONS)
def format(session: Session) -> None:
    """Auto-format code."""
    session.install("black", "isort")
    session.run("isort", "src", "tests")
    session.run("black", "src", "tests")

@session(python=PY_VERSIONS)
def typecheck_mypy(session):
    session.install("mypy", "pytest")
    session.install("pandas-stubs~=2.2")  # match your pandas version
    session.install(".")
    # If stubs are needed, install them too, e.g.:
    # session.install("types-requests", "types-python-dateutil")
    session.run("mypy", "--config-file", "pyproject.toml")

@session(python=PY_VERSIONS)
def lint(session: Session) -> None:
    """Run linters/formatters managed by Poetry dev deps."""
    session.install("ruff", "black", "isort")
    session.run("ruff", "check", "src", "tests")
    session.run("isort", "--check-only", "src", "tests")
    session.run("black", "--check", "src", "tests")

@session(python=PY_VERSIONS)
def tests(session: Session) -> None:
    """Run the test suite with deps from poetry.lock."""
    # Install the package itself (built from the Poetry metadata)
    session.install(".")
    session.run("pytest", "-q")
