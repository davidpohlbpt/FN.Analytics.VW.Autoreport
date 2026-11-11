import datetime

from pycore.schemas import ProcessState, TrackerLoadInformation

from pptcreator.controller import graph_ppt_creation


def main() -> None:
    load_info = TrackerLoadInformation(
        loadID=10,
        entityID=1,
        scenID=1,
        timestamp_started=datetime.datetime.now(),
        timestamp_finished=datetime.datetime.now(),
        status=ProcessState.PROCESSING,
    )

    graph_ppt_creation(load_info)


if __name__ == "__main__":
    main()
