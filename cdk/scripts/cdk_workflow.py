#!/usr/bin/env python3
import subprocess
import sys
import argparse
import os

def run_command(cmd, title=None):
    """Uruchom polecenie i wyświetl ładne nagłówki"""
    if title:
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50)

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(description='CDK Workflow Manager')
    parser.add_argument('--list', action='store_true', help='List current stacks')
    parser.add_argument('--plan', action='store_true', help='Show changes without deploying')
    parser.add_argument('--deploy', action='store_true', help='Deploy changes')
    parser.add_argument('--all', action='store_true', help='Apply to all stacks')
    parser.add_argument('stacks', nargs='*', help='Stacks to work with')

    args = parser.parse_args()

    # Lista stacków
    if args.list:
        list_stacks_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'list_stacks.py')
        run_command(['python', list_stacks_path], "LISTA STACKÓW")
        return

    # Planowanie zmian
    if args.plan:
        if args.all or not args.stacks:
            run_command(['cdk', 'diff'], "PLANOWANE ZMIANY (WSZYSTKIE STACKI)")
        else:
            for stack in args.stacks:
                run_command(['cdk', 'diff', stack], f"PLANOWANE ZMIANY: {stack}")

    # Wdrożenie zmian
    if args.deploy:
        deploy_cmd = ['cdk', 'deploy']

        if args.all:
            deploy_cmd.append('--all')
        elif args.stacks:
            deploy_cmd.extend(args.stacks)
        else:
            deploy_cmd.append('--all')

        # Dodatkowe flagi
        if input("Czy chcesz potwierdzać każdą zmianę? (t/N): ").lower() != 't':
            deploy_cmd.append('--require-approval=never')

        run_command(deploy_cmd, "WDRAŻANIE ZMIAN")

if __name__ == "__main__":
    main()