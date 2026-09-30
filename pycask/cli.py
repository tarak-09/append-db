import argparse
import sys
import os
from pycask.core import PyCask

def main():
    parser = argparse.ArgumentParser(description="PyCask Key-Value Store CLI")
    parser.add_argument('-d', '--dir', default='./pycask_data', help="Directory to store data files")
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Set
    set_parser = subparsers.add_parser('set', help='Set a key-value pair')
    set_parser.add_argument('key', help='Key string')
    set_parser.add_argument('value', help='Value string')
    
    # Get
    get_parser = subparsers.add_parser('get', help='Get a value by key')
    get_parser.add_argument('key', help='Key string')
    
    # Delete
    delete_parser = subparsers.add_parser('delete', help='Delete a key')
    delete_parser.add_argument('key', help='Key string')
    
    # Compact
    compact_parser = subparsers.add_parser('compact', help='Compact data files')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    with PyCask(args.dir) as db:
        if args.command == 'set':
            db.set(args.key.encode('utf-8'), args.value.encode('utf-8'))
            print(f"OK: Set '{args.key}'")
        elif args.command == 'get':
            value = db.get(args.key.encode('utf-8'))
            if value is None:
                print(f"NOT FOUND: '{args.key}'")
                sys.exit(1)
            else:
                print(value.decode('utf-8', errors='replace'))
        elif args.command == 'delete':
            db.delete(args.key.encode('utf-8'))
            print(f"OK: Deleted '{args.key}'")
        elif args.command == 'compact':
            db.compact()
            print("OK: Compaction complete")

if __name__ == '__main__':
    main()
