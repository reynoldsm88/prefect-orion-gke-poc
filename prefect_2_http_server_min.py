from flask import request
from flask_api import FlaskAPI
from prefect import flow, get_run_logger

application = FlaskAPI(__name__)

@flow(name="prefect_2_http_server")
def process_request(data):
    logger = get_run_logger()
    logger.info("new prefect_2_http_server flow : {}".format(data))

@application.route('/event', methods=['POST'])
def push_event():
    process_request(request.data)
    return {
        "ok": True
    }

if __name__ == '__main__':
    application.run(host='0.0.0.0', debug=True, port=8080)
