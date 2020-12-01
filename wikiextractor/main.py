import os
import sys
import argparse
import logging
from multiprocessing import cpu_count

from wikiextractor.process import process_dump
from wikiextractor.utils import size2integer

# constants
FORMAT_LOGGING = '%(levelname)s: %(message)s'
MIN_FILE_SIZE = 200 * 1024

logging.basicConfig(format=FORMAT_LOGGING)
logging.getLogger().setLevel(logging.INFO)


def main():
    """
    Wikipedia Extractor
    
    Extracts and cleans text from a Wikipedia database dump and stores output in a
    number of files of similar size in a given directory.
    Each file will contain several documents in the format:

        <doc id="" url="" title="">
            ...
            </doc>

    This version performs template expansion by preprocesssng the whole dump and
    collecting template definitions.
    """

    parser = argparse.ArgumentParser(prog=os.path.basename(sys.argv[0]),
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=__doc__)
    parser.add_argument("input_file",
                        help="XML wiki dump file")

    groupO = parser.add_argument_group('Output')
    groupO.add_argument("-o", "--output", default="text",
                        help="directory for extracted files (or '-' for dumping to stdout)")
    groupO.add_argument("-b", "--bytes", default="1M",
                        help="maximum bytes per output file (default %(default)s)",
                        metavar="n[KMG]")
    groupO.add_argument("-c", "--compress", action="store_true",
                        help="compress output files using bzip")
    groupO.add_argument("-k", "--keep_doc_tag", action="store_true",
                        help="keep document tag in output")

    groupP = parser.add_argument_group('Processing')
    groupP.add_argument("-ns", "--namespaces", default="", metavar="ns1,ns2",
                        help="accepted namespaces")
    groupP.add_argument("--escape_doc", action="store_true",
                        help="use to escape the contents of the output <doc>...</doc>")

    parser.add_argument("--processes", type=int, default=cpu_count(),
                        help="Number of processes to use (default %(default)s)")

    args = parser.parse_args()

    # We include as default Template, when loading external template file.
    args.knownNamespaces = set(['Template'])

    if args.namespaces:
        args.acceptedNamespaces = set(args.namespaces.split(','))
    else:
        args.acceptedNamespaces = ['w', 'wiktionary', 'wikt']

    # The namespace used for template definitions
    # It is the name associated with namespace key=10 in the siteinfo header.
    args.templateNamespace = ''
    args.templatePrefix = ''

    # The namespace used for module definitions
    # It is the name associated with namespace key=828 in the siteinfo header.
    args.moduleNamespace = ''

    # Convert size to integers
    args.file_size = size2integer(args.bytes, minimum=MIN_FILE_SIZE)

    if args.output != '-':
        assert not os.path.isdir(args.output), (
            f"Output folder {args.output} does already exist!"
        )
        os.makedirs(args.output)

    process_dump(args)

if __name__ == '__main__':
    main()
