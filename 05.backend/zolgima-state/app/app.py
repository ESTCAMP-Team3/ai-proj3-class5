import logging
from config import LOGGER_NAME
from db import create_mysql_engine
from control_service import ControlService

logger = logging.getLogger(LOGGER_NAME)

def main():
    logger.info("Starting Zolgima State Service (FSM) ...")
    engine = create_mysql_engine()
    service = ControlService(engine)
    service.start()

if __name__ == "__main__":
    main()
