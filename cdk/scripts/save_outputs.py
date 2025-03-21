import json
import boto3
import os
from datetime import datetime

def save_stack_outputs():
    cf = boto3.client('cloudformation')

    # Aktualizacja listy stacków
    stacks = [
        'VPCStack',
        'MSKStack',
        'CoreStack',
        'SearchStack',
        'BedrockStack',
        'EC2Stack'
    ]

    outputs = {}

    for stack_name in stacks:
        try:
            response = cf.describe_stacks(StackName=stack_name)
            stack = response['Stacks'][0]

            # Sprawdź czy stack istnieje i ma outputy
            if 'Outputs' in stack:
                outputs[stack_name] = {
                    output['OutputKey']: output['OutputValue']
                    for output in stack['Outputs']
                }
                print(f"✅ Pobrano outputy dla {stack_name}")
            else:
                print(f"⚠️  Brak outputów dla {stack_name}")

        except cf.exceptions.ClientError as e:
            if 'Stack with id {} does not exist'.format(stack_name) in str(e):
                print(f"⚠️  Stack {stack_name} jeszcze nie istnieje")
            else:
                print(f"❌ Błąd podczas pobierania {stack_name}: {e}")
        except Exception as e:
            print(f"❌ Nieoczekiwany błąd dla {stack_name}: {e}")

    if not outputs:
        print("❌ Nie znaleziono żadnych outputów. Czy stacki zostały wdrożone?")
        return

    # Zapisz do pliku
    config_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'config')
    os.makedirs(config_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    config_file = os.path.join(config_dir, f'stack_outputs_{timestamp}.json')

    with open(config_file, 'w') as f:
        json.dump(outputs, f, indent=2)
    print(f"\n✅ Zapisano outputy do {config_file}")

    # Stwórz też plik .env dla aplikacji
    env_file = os.path.join(config_dir, '.env')
    with open(env_file, 'w') as f:
        f.write(f"# Automatycznie wygenerowane {timestamp}\n")
        f.write(f"AWS_REGION={boto3.session.Session().region_name}\n")

        # Bezpieczne pobieranie wartości
        if 'IoTCoreStack' in outputs:
            endpoint = outputs['IoTCoreStack'].get('IoTEndpoint', '')
            if endpoint:
                f.write(f"IOT_ENDPOINT={endpoint}\n")

        if 'IoTMSKStack' in outputs:
            cluster_arn = outputs['IoTMSKStack'].get('MSKClusterArn', '')
            brokers = outputs['IoTMSKStack'].get('MSKBootstrapBrokers', '')
            if cluster_arn:
                f.write(f"MSK_CLUSTER_ARN={cluster_arn}\n")
            if brokers:
                f.write(f"MSK_BOOTSTRAP_BROKERS={brokers}\n")

        if 'IoTOpenSearchStack' in outputs:
            opensearch = outputs['IoTOpenSearchStack'].get('OpenSearchEndpoint', '')
            if opensearch:
                f.write(f"OPENSEARCH_ENDPOINT={opensearch}\n")

        if 'IoTEC2Stack' in outputs:
            publisher_ip = outputs['IoTEC2Stack'].get('PublisherPublicIP', '')
            if publisher_ip:
                f.write(f"PUBLISHER_IP={publisher_ip}\n")
                f.write(f"PUBLISHER_SSH=ec2-user@{publisher_ip}\n")

    print(f"✅ Zapisano zmienne środowiskowe do {env_file}")

if __name__ == "__main__":
    save_stack_outputs()