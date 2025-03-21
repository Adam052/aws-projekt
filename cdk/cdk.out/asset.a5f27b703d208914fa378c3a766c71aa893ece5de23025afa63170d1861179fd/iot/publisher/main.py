import json
import time
import random
import logging
from datetime import datetime, timedelta
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
import socket
import os
from dotenv import load_dotenv
import boto3

# Konfiguracja loggera
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv()

class BaseDeviceSimulator:
    def __init__(self, device_id="rpi5_001"):
        self.device_id = device_id

    def generate_sensor_data(self):
        """Generuje realistyczne dane sensorów"""
        return {
            "device_id": self.device_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "sensors": {
                "temperature": round(random.uniform(20.0, 30.0), 1),
                "humidity": round(random.uniform(40.0, 60.0), 1),
                "pressure": round(random.uniform(1000.0, 1020.0), 2),
                "orientation": {
                    "pitch": round(random.uniform(-1.0, 1.0), 1),
                    "roll": round(random.uniform(-1.0, 1.0), 1),
                    "yaw": round(random.uniform(0, 360.0), 1)
                }
            }
        }

class KafkaDeviceSimulator(BaseDeviceSimulator):
    def __init__(self, device_id="rpi5_001"):
        super().__init__(device_id)
        self.topic = 'iot-data'

        logger.info("Starting KafkaDeviceSimulator")
        logger.info(f"Device ID: {device_id}")
        logger.info(f"Topic: {self.topic}")

        # Pobierz brokers z MSK lub z zmiennej środowiskowej
        cluster_arn = os.getenv('MSK_CLUSTER_ARN')
        region = os.getenv('AWS_REGION')

        logger.debug("Environment variables:")
        logger.debug(f"MSK_CLUSTER_ARN: {cluster_arn}")
        logger.debug(f"AWS_REGION: {region}")

        # Zawsze próbuj pobrać przez API
        logger.info("Getting brokers from AWS API")
        kafka_client = boto3.client('kafka', region_name=region)
        try:
            response = kafka_client.get_bootstrap_brokers(ClusterArn=cluster_arn)
            bootstrap_servers = response['BootstrapBrokerStringTls']
            logger.info("Successfully connected to MSK brokers")
            logger.debug(f"Bootstrap servers: {bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to get brokers: {e}")
            raise

        # Konfiguracja producenta Kafka
        producer_config = {
            'bootstrap.servers': bootstrap_servers,
            'client.id': socket.gethostname(),
            'security.protocol': 'SSL',
            'ssl.ca.location': '/etc/ssl/certs/ca-bundle.crt'
        }

        logger.debug(f"Producer config: {producer_config}")
        self.producer = Producer(producer_config)
        logger.info("Producer created successfully")
        self.create_topic_if_not_exists()

    def delivery_callback(self, err, msg):
        if err:
            logger.error(f"Message delivery failed: {err}")

    def publish_data(self, data):
        """Publikuje dane bezpośrednio do Kafki"""
        try:
            logger.info(f"\n=== Publishing data to Kafka ===")
            logger.info(f"Topic: {self.topic}")
            logger.info(f"Data: {data}")

            self.producer.produce(
                self.topic,
                key=self.device_id,
                value=json.dumps(data),
                callback=self.delivery_callback
            )
            self.producer.flush()
            logger.info(f"Published data to Kafka successfully")
        except Exception as e:
            logger.error(f"Error publishing to Kafka: {e}")
            raise

    def create_topic_if_not_exists(self):
        """Tworzy temat Kafka, jeśli nie istnieje"""
        try:
            from confluent_kafka.admin import AdminClient, NewTopic

            # Zamiast używać self.producer.conf, użyj tej samej konfiguracji co dla producenta
            bootstrap_servers = os.getenv('MSK_BOOTSTRAP_BROKERS')

            admin_client = AdminClient({
                'bootstrap.servers': bootstrap_servers,
                'security.protocol': 'SSL',
                'ssl.ca.location': '/etc/ssl/certs/ca-bundle.crt'
            })

            # Sprawdź, czy temat istnieje
            metadata = admin_client.list_topics(timeout=10)
            if self.topic in metadata.topics:
                logger.info(f"Topic {self.topic} already exists")
                return

            # Utwórz temat
            new_topic = NewTopic(
                self.topic,
                num_partitions=1,
                replication_factor=2
            )

            result = admin_client.create_topics([new_topic])
            for topic, future in result.items():
                try:
                    future.result()  # Czekaj na wynik
                    logger.info(f"Topic {topic} created")
                except Exception as e:
                    if "TopicExistsError" in str(e):
                        logger.info(f"Topic {topic} already exists")
                    else:
                        logger.error(f"Failed to create topic {topic}: {e}")
        except Exception as e:
            logger.error(f"Error creating topic: {e}")

class IoTDeviceSimulator(BaseDeviceSimulator):
    def __init__(self, device_id="rpi5_001"):
        super().__init__(device_id)
        self.iot_endpoint = os.getenv('IOT_ENDPOINT')
        self.region = os.getenv('AWS_REGION', 'eu-central-1')

        self.iot_client = boto3.client('iot-data',
            endpoint_url=f"https://{self.iot_endpoint}",
            region_name=self.region
        )
        self.topic = f'iot/data/{device_id}'

    def publish_data(self, data):
        """Publikuje dane do AWS IoT Core"""
        try:
            response = self.iot_client.publish(
                topic=self.topic,
                qos=1,
                payload=json.dumps(data)
            )
            logger.info(f"Opublikowano dane do IoT Core: {data}")
            return response
        except Exception as e:
            logger.error(f"Błąd publikacji do IoT Core: {e}")
            return None

def get_simulator():
    """Fabryka symulatorów - wybiera odpowiedni typ na podstawie konfiguracji"""
    use_iot_core = os.getenv('USE_IOT_CORE', 'false').lower() == 'true'
    device_id = os.getenv('DEVICE_ID', 'rpi5_001')

    if use_iot_core and os.getenv('IOT_ENDPOINT'):
        return IoTDeviceSimulator(device_id)
    return KafkaDeviceSimulator(device_id)

def main():
    simulator = get_simulator()
    logger.info("=== Starting IoT data publisher ===")
    end_time = datetime.now() + timedelta(minutes=1)  # Działaj przez 1 minutę

    while datetime.now() < end_time:
        data = simulator.generate_sensor_data()
        try:
            simulator.publish_data(data)

            time.sleep(1)  # 1 pomiar na sekundę

        except Exception as e:
            logger.error(f"Error: {e}")

    logger.info("=== Finished publishing data ===")
    if hasattr(simulator, 'producer'):
        simulator.producer.flush()

if __name__ == "__main__":
    main()