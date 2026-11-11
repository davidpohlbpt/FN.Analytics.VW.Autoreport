from pycore.api.web.app import app
from pycore.easy import hook_repo

from pptcreator import controller

PPT_CREATION = "CreatePPT"

hook_repo.hook_in_process(PPT_CREATION, controller.graph_ppt_creation)
