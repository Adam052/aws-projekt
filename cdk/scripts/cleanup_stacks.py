import boto3
import time
import subprocess

def wait_for_opensearch_deletion(opensearch_client, domain_name, max_attempts=20):
    print(f"Czekam na usunięcie domeny OpenSearch {domain_name}...")
    for i in range(max_attempts):
        try:
            # Sprawdź czy domena wciąż istnieje
            opensearch_client.describe_domain(DomainName=domain_name)
            print(f"Domena wciąż istnieje, czekam... ({i+1}/{max_attempts})")
            time.sleep(30)
        except opensearch_client.exceptions.ResourceNotFoundException:
            print(f"✅ Domena {domain_name} została usunięta")
            return True
    return False

def delete_network_interfaces():
    ec2 = boto3.client('ec2')
    try:
        # Pobierz VPC ID z tagu
        vpcs = ec2.describe_vpcs(
            Filters=[{'Name': 'tag:Name', 'Values': ['*VPCStack*']}]
        )['Vpcs']
        if not vpcs:
            print("⚠️  Nie znaleziono VPC")
            return
        vpc_id = vpcs[0]['VpcId']

        # Znajdź i usuń interfejsy sieciowe
        enis = ec2.describe_network_interfaces(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )['NetworkInterfaces']

        for eni in enis:
            try:
                print(f"Usuwanie ENI {eni['NetworkInterfaceId']}...")
                ec2.delete_network_interface(NetworkInterfaceId=eni['NetworkInterfaceId'])
            except Exception as e:
                print(f"⚠️  Nie można usunąć ENI {eni['NetworkInterfaceId']}: {e}")
    except Exception as e:
        print(f"⚠️  Błąd podczas usuwania ENI: {e}")

def delete_stacks():
    cf = boto3.client('cloudformation')
    ec2 = boto3.client('ec2')
    opensearch = boto3.client('opensearch')

    # Najpierw usuń domenę OpenSearch
    try:
        domains = opensearch.list_domain_names()
        for domain in domains['DomainNames']:
            if 'iot' in domain['DomainName'].lower():
                domain_name = domain['DomainName']
                print(f"Usuwanie domeny OpenSearch {domain_name}...")
                opensearch.delete_domain(DomainName=domain_name)

                # Czekaj na faktyczne usunięcie domeny
                if not wait_for_opensearch_deletion(opensearch, domain_name):
                    print("⚠️ Przekroczono limit czasu oczekiwania na usunięcie domeny")
                    continue
    except Exception as e:
        print(f"Błąd podczas usuwania domeny OpenSearch: {e}")

    # Najpierw usuń klaster MSK (jeśli istnieje)
    kafka = boto3.client('kafka')
    try:
        clusters = kafka.list_clusters()['ClusterInfoList']
        for cluster in clusters:
            if 'iot-msk-cluster' in cluster['ClusterName']:
                print(f"Usuwanie klastra MSK {cluster['ClusterName']}...")
                kafka.delete_cluster(ClusterArn=cluster['ClusterArn'])
    except Exception as e:
        print(f"Błąd podczas usuwania klastra MSK: {e}")

    # 1. Najpierw usuń ENIs
    try:
        enis = ec2.describe_network_interfaces(
            Filters=[{
                'Name': 'subnet-id',
                'Values': ['subnet-05c786002f698385f']
            }]
        )['NetworkInterfaces']

        for eni in enis:
            try:
                print(f"Usuwanie ENI {eni['NetworkInterfaceId']}...")
                ec2.delete_network_interface(
                    NetworkInterfaceId=eni['NetworkInterfaceId']
                )
            except Exception as e:
                print(f"Błąd podczas usuwania ENI: {e}")
    except Exception as e:
        print(f"Błąd podczas listowania ENI: {e}")

    # 2. Poczekaj na usunięcie ENI
    time.sleep(30)

    # 3. Usuń stacki w odpowiedniej kolejności
    stacks_to_delete = ['EC2Stack', 'MSKStack']

    for stack_name in stacks_to_delete:
        try:
            print(f"Usuwanie stacka {stack_name}...")
            cf.delete_stack(StackName=stack_name)
            waiter = cf.get_waiter('stack_delete_complete')
            waiter.wait(
                StackName=stack_name,
                WaiterConfig={'Delay': 30, 'MaxAttempts': 20}
            )
            print(f"✅ Stack {stack_name} usunięty")

            # Dodaj dodatkowe opóźnienie między usuwaniem stacków
            if stack_name == 'EC2Stack':
                print("Czekam na pełne usunięcie EC2Stack przed usunięciem MSKStack...")
                time.sleep(60)

        except Exception as e:
            print(f"⚠️ Błąd podczas usuwania {stack_name}: {e}")
            break  # Przerwij usuwanie kolejnych stacków jeśli wystąpił błąd

    # 2. Poczekaj na usunięcie zależnych stacków
    time.sleep(60)

    # 3. Teraz spróbuj usunąć VPC Stack
    try:
        print("Usuwanie VPC Stack...")
        cf.delete_stack(StackName='VPCStack')
        waiter = cf.get_waiter('stack_delete_complete')
        waiter.wait(StackName='VPCStack', WaiterConfig={'Delay': 30, 'MaxAttempts': 20})
        print("✅ VPC Stack usunięty")
    except Exception as e:
        print(f"⚠️ Błąd podczas usuwania VPC Stack: {e}")

        # 4. Jeśli nie udało się usunąć VPC, spróbuj wymusić usunięcie
        try:
            vpc_response = ec2.describe_vpcs(
                Filters=[{'Name': 'tag:Name', 'Values': ['*VPCStack*']}]
            )
            if vpc_response['Vpcs']:
                vpc_id = vpc_response['Vpcs'][0]['VpcId']
                print(f"Próba wyczyszczenia VPC {vpc_id}...")

                # Usuń wszystkie subnety
                subnets = ec2.describe_subnets(
                    Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
                )['Subnets']
                for subnet in subnets:
                    print(f"Usuwanie subnetu {subnet['SubnetId']}...")
                    ec2.delete_subnet(SubnetId=subnet['SubnetId'])

                # Usuń VPC
                print(f"Usuwanie VPC {vpc_id}...")
                ec2.delete_vpc(VpcId=vpc_id)
                print("✅ VPC usunięte ręcznie")
        except Exception as e:
            print(f"⚠️ Błąd podczas ręcznego usuwania VPC: {e}")

if __name__ == "__main__":
    delete_stacks()