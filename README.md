# WikiExtractor

Package forked from the original repo and tried to reduce the number of bugsss...

The tool is written in Python and requires Python 3 but no additional library.

# Details

WikiExtractor performs template expansion by preprocessing the whole dump and extracting template definitions.

In order to speed up processing:

- multiprocessing is used for dealing with articles in parallel
- a cache is kept of parsed templates (only useful for repeated extractions).

## Installation

The script may be invoked directly with:

```bash
python -m wikiextractor.main
```

Install from here with
```bash
pip install git+https://github.com/lucadiliello/wikiextractor.git --upgrade
```

## Usage

### Wikiextractor
The script is invoked with a Wikipedia dump file as an argument:

```bash
python -m wikiextractor.main <Wikipedia dump file>
````

The output is stored in several files of similar size in a given directory.
Each file will contains several documents containing only simple `<doc>` tags.

Usage:
```bash
main.py [-h] [-o OUTPUT] [-b n[KMG]] [-c] [-ns ns1,ns2] [--processes PROCESSES] input
```

### Arguments

- `input`: XML wiki dump file
- `-h`, `--help`: show this help message and exit
- `--processes PROCESSES`: Number of processes to use (default 1)
- `-o OUTPUT`, `--output OUTPUT`: directory for extracted files (or '-' for dumping to stdout)
- `-b n[KMG]`, `--bytes n[KMG]`: maximum bytes per output file (default 1M)
- `-c`, `--compress` compress output files using bzip
- `-ns ns1,ns2`, `--namespaces ns1,ns2`: accepted namespaces in links
  
### Output
Extracts and cleans text from a Wikipedia database dump and stores output in a
number of files of similar size in a given directory.
Each file will contain several documents in the format:

```xml
<doc id="" revid="" url="" title="">
    ...
</doc>
```


## License
The code is made available under the [GNU Affero General Public License v3.0](LICENSE). 

## Reference
If you find this code useful, please refer it in publications as:

~~~
@misc{Wikiextractor2015,
  author = {Giusepppe Attardi},
  title = {WikiExtractor},
  year = {2015},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/attardi/wikiextractor}}
}
~~~
