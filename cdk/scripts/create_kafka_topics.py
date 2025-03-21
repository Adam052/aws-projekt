#!/usr/bin/env python3
import boto3
import subprocess
import os
import time
import json

def get_msk_bootstrap_brokers():
    """Pobierz bootstrap brokers z MSK"""
    msk = boto3.client('kafka')

    # Pobierz listę klastrów
    clusters = msk.list_clusters()['ClusterInfoList']

    # Znajdź klaster MSK
    for cluster in clusters:
        if 'msk-' in cluster['ClusterName'].lower():
            cluster_arn = cluster['ClusterArn']
            print(f"Znaleziono klaster MSK: {cluster['ClusterName']}")

            # Pobierz bootstrap brokers
            brokers = msk.get_bootstrap_brokers(ClusterArn=cluster_arn)
            return brokers['BootstrapBrokerStringTls']

    print("Nie znaleziono klastra MSK")
    return None

def create_topics():
    """Utwórz tematy Kafka"""
    bootstrap_brokers = get_msk_bootstrap_brokers()

    if not bootstrap_brokers:
        print("Nie można utworzyć tematów - brak bootstrap brokers")
        return False

    print(f"Bootstrap brokers: {bootstrap_brokers}")

    # Lista tematów do utworzenia
    topics = ["iot-data", "iot-processed"]

    # Utwórz tematy
    for topic in topics:
        try:
            print(f"Tworzenie tematu: {topic}")

            # Użyj AWS CLI do utworzenia tematu
            cmd = [
                "aws", "kafka", "create-topic",
                "--bootstrap-broker", bootstrap_brokers,
                "--topic", topic,
                "--partitions", "1",
                "--replication-factor", "2"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"✅ Temat {topic} utworzony pomyślnie")
            else:
                print(f"❌ Błąd podczas tworzenia tematu {topic}: {result.stderr}")

                # Sprawdź czy temat już istnieje
                if "TopicAlreadyExists" in result.stderr:
                    print(f"ℹ️ Temat {topic} już istnieje")
                    continue

                return False
        except Exception as e:
            print(f"❌ Nieoczekiwany błąd podczas tworzenia tematu {topic}: {e}")
            return False

    return True

if __name__ == "__main__":
    print("Tworzenie tematów Kafka...")
    success = create_topics()

    if success:
        print("✅ Wszystkie tematy zostały utworzone")
    else:
        print("❌ Wystąpiły błędy podczas tworzenia tematów")