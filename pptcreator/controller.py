import logging

from pycore.schemas import TrackerLoadInformation

from pptcreator.creator.graph_steer_creation_process import graph_steer_creation_process


def graph_ppt_creation(load_info: TrackerLoadInformation):
    logging.info(f"Starting PPT creation for load_info: {load_info}")
    graph_steer_creation_process(load_info)
