"""The used car listing project's configuration layer.

The project layer of the cascade described in `serespar/config.py`: what every
parser modelling used car listings shares, and the place its default values
live instead of sitting as literals in the code.

It subclasses serespar's `ProjectSettings` rather than `ProjectConfig`, so the
layer can be built straight from the environment (`SERESPAR_DB_HOST`, ...).
"""

from serespar.config import ProjectSettings


class UsedCarListingProjectConfig(ProjectSettings):
    """`ProjectConfig` for the used car listing project.

    Every parser under this project writes into the same schema, so the
    database name defaults here; `SERESPAR_DB_NAME` still overrides it.
    """

    db_name: str = "used_cars"
