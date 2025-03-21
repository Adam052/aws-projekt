import json
import time
import boto3
import logging
from datetime import datetime, timedelta
from confluent_kafka import Consumer, KafkaError
import os
from dotenv import load_dotenv

# Konfiguracja loggera
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Ładuj zmienne środowiskowe
load_dotenv()

class IoTDataProcessor:
    def __init__(self):
        logger.info("Initializing IoT Data Processor")

        # Inicjalizacja klienta S3
        self.s3_client = boto3.client('s3')
        self.bucket_name = os.getenv('S3_BUCKET_NAME')
        logger.info(f"Using S3 bucket: {self.bucket_name}")
        if not self.bucket_name:
            raise ValueError("S3_BUCKET_NAME environment variable is not set!")

        # Pobierz brokers z MSK
        cluster_arn = os.getenv('MSK_CLUSTER_ARN')
        region = os.getenv('AWS_REGION')

        logger.info("Getting brokers from AWS API")
        logger.debug(f"MSK_CLUSTER_ARN: {cluster_arn}")
        logger.debug(f"AWS_REGION: {region}")

        kafka_client = boto3.client('kafka', region_name=region)
        try:
            response = kafka_client.get_bootstrap_brokers(ClusterArn=cluster_arn)
            bootstrap_servers = response['BootstrapBrokerStringTls']
            logger.info(f"Successfully connected to MSK brokers")
            logger.debug(f"Bootstrap servers: {bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to get brokers: {e}")
            raise

        # Konfiguracja Kafka Consumer
        consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': 'iot-processor-group',
            'auto.offset.reset': 'earliest',
            'security.protocol': 'SSL',
            'ssl.ca.location': '/etc/ssl/certs/ca-bundle.crt'
        }

        self.consumer = Consumer(consumer_config)
        self.topic = 'iot-data'
        self.consumer.subscribe([self.topic])
        logger.info(f"Subscribed to topic: {self.topic}")

    def save_to_s3(self, data):
        """Zapisz dane do S3"""
        try:
            # Generuj nazwę pliku na podstawie timestampa
            timestamp = datetime.now().strftime('%Y/%m/%d/%H/%M_%S.json')
            key = f'raw-data/{timestamp}'

            # Zapisz do S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(data)
            )
            logger.info(f"Data saved to S3: s3://{self.bucket_name}/{key}")
            logger.debug(f"Data content: {json.dumps(data, indent=2)}")
        except Exception as e:
            logger.error(f"Failed to save data to S3: {str(e)}")
            logger.error(f"Bucket: {self.bucket_name}, Key: {key}")
            logger.exception("Full traceback:")

    def process_messages(self):
        """Główna pętla przetwarzania wiadomości"""
        logger.info("Starting message processing")

        while True:
            try:
                msg = self.consumer.poll(1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error(f'Consumer error: {msg.error()}')
                    continue

                data = json.loads(msg.value().decode('utf-8'))
                logger.info(f"Received data: {json.dumps(data, indent=2)}")

                # Zapisz do S3
                self.save_to_s3(data)

            except Exception as e:
                logger.error(f"Error processing message: {e}")
                time.sleep(5)  # Czekaj przed ponowną próbą

def main():
    processor = IoTDataProcessor()
    processor.process_messages()

if __name__ == "__main__":
    main()