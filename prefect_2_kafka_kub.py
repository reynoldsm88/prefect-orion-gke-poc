import io
import json
import os
import sys

from confluent_kafka import Consumer, KafkaError, KafkaException
from prefect import flow, task, get_run_logger
from prefect.blocks.storage import GoogleCloudStorageBlock
from prefect.deployments import DeploymentSpec
from prefect.flow_runners import KubernetesFlowRunner

class TopicConsumer:

    def __init__(self, topics, config, commits_every_n_messages=1):
        self.topics = topics
        self.config = config
        self.commits_every_n_messages = commits_every_n_messages
        self.consumer = Consumer(config)
        self.running = False

    def consume(self):
        try:
            self.consumer.subscribe(self.topics)
            print("Subscribed to topics: {}".format(self.topics))
            self.running = True
            msg_count = 0
            while self.running:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition event
                        sys.stderr.write('%% %s [%d] reached end at offset %d\n' %
                                         (msg.topic(), msg.partition(), msg.offset()))
                    elif msg.error():
                        raise KafkaException(msg.error())
                else:
                    yield msg
                    msg_count += 1
                    if msg_count % self.commits_every_n_messages == 0:
                        self.consumer.commit(asynchronous=False)
        finally:
            # Close down consumer to commit final offsets.
            self.consumer.close()

    def shutdown(self):
        self.running = False

@task
def process_message(msg):
    logger = get_run_logger()
    logger.info("Received message topic={} partition={} offset={} key={} value={}".format(
        msg.topic(), msg.partition(), msg.offset(), msg.key(), msg.value()))

@flow(name="prefect_2_kafka_kub")
def main():

    conf = {
        'bootstrap.servers': "xxxxx",
        'group.id': "prefect_poc_kafka",
        'auto.offset.reset': 'earliest',
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'PLAIN',
        'sasl.username' :'xxxxx',
        'sasl.password': 'xxxxx'
    }

    topic_consumer = TopicConsumer(
        ["prefect-poc"],
        conf
    )

    for msg in topic_consumer.consume():
        process_message(msg)

    topic_consumer.shutdown()

DeploymentSpec(
    name="gcs",
    flow=main,
    tags=["kubernetes"],
    flow_storage=GoogleCloudStorageBlock(
        bucket="prefect-poc"
    ),
    flow_runner=KubernetesFlowRunner(
        image="gcr.io/everysens-integration/prefect-poc/development:latest",
        namespace="everysens",
        service_account_name="prefect-orion-agent"
    ),
)

if __name__ == '__main__':
    main()
