"""
Entry point for the studyassistant Streamlit app.

This module simply imports the main Streamlit application defined in the
``studyassistant.main`` package. Importing that module has the side effect
of running the Streamlit app because the logic is executed at the module
level. Having this thin wrapper allows deployments (such as on
Streamlit Community Cloud) to reference ``main.py`` at the project root
without duplicating code.
"""

# Importing the internal package will execute the Streamlit application.
import studyassistant.main  # noqa: F401


def main() -> None:
    """Dummy main function to satisfy runtime environments.

    Importing ``studyassistant.main`` runs the app, but some runtime
    environments may expect a callable named ``main``. This function
    intentionally does nothing because the application logic is executed
    during import.
    """
    return None


if __name__ == "__main__":
    main()
