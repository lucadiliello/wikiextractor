import fileinput
import logging
import re
import sys
from io import StringIO
from multiprocessing import Process, Queue
from timeit import default_timer

import tqdm

from wikiextractor.clean import Extractor
from wikiextractor.regex import tag_regex
from wikiextractor.utils import hook_compressed_encoded
from wikiextractor.writer import NextFile, OutputSplitter


def process_dump(args):
    """
    Args must contain:
        :param input_file: name of the wikipedia dump file; '-' to read from stdin
        :param template_file: optional file with template definitions.
        :param output: directory where to store extracted data, or '-' for stdout
        :param file_size: max size of each extracted file, or None for no max (one file)
        :param compress: whether to compress files with bzip.
        :param process_count: number of extraction processes to spawn.
    """

    # Define input stream
    if args.input_file == '-':
        input = sys.stdin
    else:
        input = fileinput.FileInput(args.input_file, openhook=hook_compressed_encoded)

    # Collect siteinfo
    for line in tqdm.tqdm(input, desc="Reading dump siteinfo"):
        tags = tag_regex.search(line)

        if tags:
            tag = tags.group(2)

            if tag == 'base':
                # discover urlbase from the xml dump file
                # /mediawiki/siteinfo/base
                base = tags.group(3)
                args.urlbase = base[:base.rfind("/")]

            elif tag == 'namespace':
                args.knownNamespaces.add(tags.group(3))
                if re.search('key="10"', line):
                    args.templateNamespace = tags.group(3)
                    args.templatePrefix = args.templateNamespace + ':'
                elif re.search('key="828"', line):
                    args.moduleNamespace = tags.group(3)
                    args.modulePrefix = args.moduleNamespace + ':'

            elif tag == '/siteinfo':
                break

    # process pages
    logging.info("Starting page extraction from %s.", args.input_file)
    extract_start = default_timer()

    # Parallel Map/Reduce:
    # - pages to be processed are dispatched to workers
    # - a reduce process collects the results, sort them and print them.

    maxsize = 10 * args.processes

    # output queue
    output_queue = Queue(maxsize=maxsize)
    results_queue = Queue()

    # Reduce job that sorts and prints output
    reduce = Process(target=reduce_process, args=(output_queue, results_queue))
    reduce.start()

    # initialize jobs queue
    jobs_queue = Queue(maxsize=maxsize)

    # start worker processes
    logging.info("Using %d extract processes.", args.processes)
    workers = []
    for _ in range(max(1, args.processes)):
        extractor = Process(target=extract_process,
                            args=(args, jobs_queue, output_queue))
        extractor.daemon = True  # only live while parent process lives
        extractor.start()
        workers.append(extractor)

    writer = Process(target=writer_process,
                     args=(results_queue, args.output, args.compress, args.file_size))
    writer.start()
    # Mapper process

    # we collect individual lines, since str.join() is significantly faster
    # than concatenation
    page = []
    id = None
    last_id = None
    ordinal = 0  # page count
    inText = False
    redirect = False
    title = None

    for line in input:

        if '<' not in line:  # faster than doing re.search()
            if inText:
                page.append(line)
            continue

        tags = tag_regex.search(line)
        if tags:
            tag = tags.group(2)

            if tag == 'page':
                page = []
                redirect = False

            elif tag == 'id' and not id:
                id = tags.group(3)

            elif tag == 'title':
                title = tags.group(3)

            elif tag == 'redirect':
                redirect = True

            elif tag == 'text':
                inText = True
                line = line[tags.start(3):tags.end(3)]
                page.append(line)
                if tags.lastindex == 4:  # open-close
                    inText = False

            elif tag == '/text':
                if tags.group(1):
                    page.append(tags.group(1))
                inText = False

            elif inText:
                page.append(line)

            elif tag == '/page':
                colon = title.find(':')
                if (
                    (colon < 0 or title[:colon] in args.acceptedNamespaces) and 
                    id != last_id and
                    not redirect
                ):
                    job = (id, title, page, ordinal)
                    jobs_queue.put(job)  # goes to any available extract_process
                    last_id = id
                    ordinal += 1
                id = None
                page = []

    input.close()

    # signal termination
    for _ in workers:
        jobs_queue.put(None)

    # wait for workers to terminate
    for w in workers:
        w.join()

    # signal end of work to reduce process
    output_queue.put(None)
    # wait for it to finish
    reduce.join()
    results_queue.put(None)

    extract_duration = default_timer() - extract_start
    extract_rate = ordinal / extract_duration
    logging.info("Finished %d-process extraction of %d articles in %.1fs (%.1f art/s)",
                 args.processes, ordinal, extract_duration, extract_rate)


# ----------------------------------------------------------------------
# Multiprocess support


def extract_process(args, jobs_queue, output_queue):
    """
    Pull tuples of raw page content, do CPU/regex-heavy fixup, push finished text
    :param jobs_queue: where to get jobs.
    :param output_queue: where to queue extracted text for output.
    """
    while True:
        job = jobs_queue.get()  # job is (id, title, page, ordinal)
        if job:
            out = StringIO()  # memory buffer
            Extractor(args, *job[:3]).extract(out)  # (id, title, page)
            text = out.getvalue()
            output_queue.put((job[3], text))  # (ordinal, extracted_text)
            out.close()
        else:
            break


def writer_process(results_queue, out_file, file_compress, file_size):
    """
    Write data to either the standard output or the file manager.
    """

    if out_file == '-':
        output = sys.stdout
        if file_compress:
            logging.warn("writing to stdout, so no output compression (use an external tool)")
    else:
        nextFile = NextFile(out_file)
        output = OutputSplitter(nextFile, file_size, file_compress)

    while True:
        data = results_queue.get()
        if data is None:
            if output != sys.stdout:
                output.close()
            break
        output.write(data)


def reduce_process(output_queue, results_queue):
    """
    Pull finished article text, write series of files (or stdout)
    :param output_queue: text to be output.
    :param results: output queue.
    """

    interval_start = default_timer()
    period = 100000
    # FIXME: use a heap
    ordering_buffer = {}  # collected pages
    next_ordinal = 0  # sequence number of pages
    while True:
        if next_ordinal in ordering_buffer:
            results_queue.put(ordering_buffer.pop(next_ordinal))
            # print(ordering_buffer.pop(next_ordinal))
            next_ordinal += 1
            # progress report
            if next_ordinal % period == 0:
                interval_rate = period / (default_timer() - interval_start)
                logging.info("Extracted %d articles (%.1f art/s)",
                             next_ordinal, interval_rate)
                interval_start = default_timer()
        else:
            # mapper puts None to signal finish
            pair = output_queue.get()
            if not pair:
                break
            ordinal, text = pair
            ordering_buffer[ordinal] = text
