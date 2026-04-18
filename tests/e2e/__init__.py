# End-to-end tests for ClawSocialArena v2.
#
# Tests in this package typically require Docker to be installed and a
# working compose daemon. They self-skip via ``pytestmark`` when the
# prerequisites are missing so the rest of the suite stays portable to
# developer laptops and CI lanes that do not ship a Docker engine.
