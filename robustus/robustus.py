# =============================================================================
# COPYRIGHT 2013 Brain Corporation.
# License under MIT license (see LICENSE file)
# =============================================================================

import argparse
import glob
import importlib
import logging
import os
import subprocess
import sys
from detail import Requirement, RequirementException, read_requirement_file
from detail.requirement import remove_duplicate_requirements, expand_requirements_specifiers
from detail.utility import ln, run_shell, download
import urllib2
# for doctests
import detail


class RobustusException(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class Robustus(object):
    settings_file_path = '.robustus'
    cached_requirements_file_path = 'cached_requirements.txt'
    default_settings = {
        'cache': 'wheelhouse'
    }
    # FIXME: not so great to hardcode braincorp address here, but in other way
    # we need to modify other repositories use_repo.sh which use robustus
    default_package_locations = ['http://thirdparty-packages.braincorporation.net']

    def __init__(self, args):
        """
        Initialize robustus tool. Should be called if sys.executable is in robustus environment
        @param: args - command line arguments
        """
        if args.env is not None:
            self.env = os.path.abspath(args.env)
        else:
            self.env = os.path.abspath(os.path.join(sys.executable, os.pardir, os.pardir))

        # check if we are in robustus environment
        self.settings_file_path = os.path.join(self.env, Robustus.settings_file_path)
        if not os.path.isfile(self.settings_file_path):
            raise RobustusException('bad robustus environment ' + self.env + ': .robustus settings file not found')
        settings = eval(open(self.settings_file_path).read())
        self.settings = Robustus._override_settings(settings, args)
        if 'find_links' not in self.settings:
            self.settings['find_links'] = self.default_package_locations
        logging.info('Robustus will use the following cache folder: %s' % self.settings['cache'])

        self.python_executable = os.path.join(self.env, 'bin/python')
        if not os.path.isfile(self.python_executable):
            self.python_executable = os.path.join(self.env, 'bin/python27')
        if not os.path.isfile(self.python_executable):
            raise RobustusException('bad robustus environment ' + self.env + ': python not found')

        self.pip_executable = os.path.join(self.env, 'bin/pip')
        if not os.path.isfile(self.pip_executable):
            raise RobustusException('bad robustus environment ' + self.env + ': pip not found')

        self.easy_install_executable = os.path.join(self.env, 'bin/easy_install')
        if not os.path.isfile(self.easy_install_executable):
            raise RobustusException('bad robustus environment ' + self.env + ': easy_install not found')

        # make cached packages directory if necessary
        self.cache = os.path.join(self.env, self.settings['cache'])
        if not os.path.isdir(self.cache):
            os.mkdir(self.cache)

        # read cached packages
        self.cached_packages = []
        for rob_file in glob.iglob('%s/*.rob' % self.cache):
            self.cached_packages.append(Requirement(rob_filename=rob_file))

    @staticmethod
    def _override_settings(settings, args):
        # override settings with command line arguments
        if args.cache is not None:
            settings['cache'] = args.cache
        settings['verbosity'] = args.verbosity
        settings['debug'] = args.debug

        # Set logging volume for debugging
        if settings['debug']:
            logging.getLogger('').setLevel(logging.DEBUG)
        return settings

    @staticmethod
    def env(args):
        """
        Create robustus environment.
        @param args: command line arguments
        """
        # create virtualenv
        python_executable = os.path.abspath(os.path.join(args.env, 'bin/python'))
        if os.path.isfile(python_executable):
            logging.info('Found virtualenv in ' + args.env)
        else:
            logging.info('Creating virtualenv')
            virtualenv_args = ['virtualenv', args.env, '--prompt', args.prompt]
            if args.python is not None:
                virtualenv_args += ['--python', args.python]
            if args.system_site_packages:
                virtualenv_args += ['--system-site-packages']
            subprocess.call(virtualenv_args)

        pip_executable = os.path.abspath(os.path.join(args.env, 'bin/pip'))
        if not os.path.isfile(pip_executable):
            raise RobustusException('failed to create virtualenv, pip not found')
        easy_install_executable = os.path.abspath(os.path.join(args.env, 'bin/easy_install'))
        if not os.path.isfile(easy_install_executable):
            raise RobustusException('failed to create virtualenv, easy_install not found')

        # http://wheel.readthedocs.org/en/latest/
        # wheel is binary packager for python/pip
        # we store all packages in binary wheel somewhere on the PC to avoid recompilation of packages

        # wheel needs pip>=1.4, setuptools>=0.8 and wheel packages for wheeling
        subprocess.call([pip_executable, 'install', 'pip==1.4.1', '--upgrade'])
        # some sloppy maintained packages (like ROS) require outdated distribute for installation
        # and we need to install it before setuptools
        subprocess.call([pip_executable, 'install', 'distribute==0.7.3'])
        subprocess.call([pip_executable, 'install', 'setuptools==1.1.6', '--upgrade'])
        subprocess.call([pip_executable, 'install', 'wheel==0.22.0', '--upgrade'])

        # linking BLAS and LAPACK libraries
        if os.path.isfile('/usr/lib64/libblas.so.3'):
            logging.info('Linking CentOS libblas to venv')
            blas_so = os.path.join(args.env, 'lib64/libblas.so')
            ln('/usr/lib64/libblas.so.3', blas_so, True)
            os.environ['BLAS'] = os.path.join(args.env, 'lib64')
        elif os.path.isfile('/usr/lib/libblas.so'):
            logging.info('Linking Ubuntu libblas to venv')
            blas_so = os.path.join(args.env, 'lib/libblas.so')
            ln('/usr/lib/libblas.so', blas_so, True)
            os.environ['BLAS'] = os.path.join(args.env, 'lib')

        if os.path.isfile('/usr/lib64/liblapack.so.3'):
            logging.info('Linking CentOS liblapack to venv')
            lapack_so = os.path.join(args.env, 'lib64/liblapack.so')
            ln('/usr/lib64/liblapack.so.3', lapack_so, True)
            os.environ['LAPACK'] = os.path.join(args.env, 'lib64')
        elif os.path.isfile('/usr/lib/liblapack.so'):
            logging.info('Linking Ubuntu liblapack to venv')
            lapack_so = os.path.join(args.env, 'lib/liblapack.so')
            ln('/usr/lib/liblapack.so', lapack_so, True)
            os.environ['LAPACK'] = os.path.join(args.env, 'lib')

        # readline must be come before everything else
        logging.info('Installing readline...')
        subprocess.call([easy_install_executable, '-q', 'readline==6.2.2'])

        # compose settings file
        logging.info('Write .robustus config file')
        settings = Robustus._override_settings(Robustus.default_settings, args)
        with open(os.path.join(args.env, Robustus.settings_file_path), 'w') as file:
            file.write(str(settings))

        # install robustus
        cwd = os.getcwd()
        script_dir = os.path.dirname(os.path.realpath(__file__))
        setup_dir = os.path.abspath(os.path.join(script_dir, os.path.pardir))
        os.chdir(setup_dir)
        subprocess.call([python_executable, 'setup.py', 'install'])
        os.chdir(cwd)
        logging.info('Robustus initialized environment with cache located at %s' % settings['cache'])

    def install_through_wheeling(self, requirement_specifier, rob_file, ignore_index):
        """
        Check if package cache already contains package of specified version, if so install it.
        Otherwise make a wheel and put it into cache.
        Hope manual check for requirements file won't be necessary, waiting for pip 1.5 https://github.com/pypa/pip/issues/855
        :param package: package name
        :param version: package version string
        :return: None
        """
        # if wheelhouse doesn't contain necessary requirement - make a wheel
        if self.find_satisfactory_requirement(requirement_specifier) is None:
            logging.info('Wheel not found, downloading package')
            return_code = run_shell([self.pip_executable,
                                     'install',
                                     '--download',
                                     self.cache,
                                     requirement_specifier.freeze()],
                                    shell=False,
                                    verbose=self.settings['verbosity'] >= 2)
            if return_code != 0:
                raise RequirementException('pip failed to download requirement %s' % requirement_specifier.freeze())
            logging.info('Done')

            logging.info('Building wheel')
            wheel_cmd = [self.pip_executable,
                         'wheel',
                         '--no-index',
                         '--find-links=%s' % self.cache,
                         '--wheel-dir=%s' % self.cache,
                         requirement_specifier.freeze()]
            # we probably sometimes will want to see build log
            for i in xrange(self.settings['verbosity']):
                wheel_cmd.append('-v')
            return_code = run_shell(wheel_cmd,
                                    shell=False,
                                    verbose=self.settings['verbosity'] >= 1)
            if return_code != 0:
                raise RequirementException('pip failed to build wheel for requirement %s'
                                           % requirement_specifier.freeze())
            logging.info('Done')

        # install from prebuilt wheel
        logging.info('Installing package from wheel')
        return_code = run_shell([self.pip_executable,
                                 'install',
                                 '--no-index',
                                 '--use-wheel',
                                 '--find-links=%s' % self.cache,
                                 requirement_specifier.freeze()],
                                shell=False,
                                verbose=self.settings['verbosity'] >= 2)
        if return_code != 0:
            raise RequirementException('pip failed to install requirement %s from wheels cache %s.'
                                       % (requirement_specifier.freeze(), self.cache))
        logging.info('Done')

    def install_requirement(self, requirement_specifier, ignore_index):
        logging.info('Installing ' + requirement_specifier.freeze())

        if requirement_specifier.url is not None or requirement_specifier.path is not None:
            # install reqularly using pip
            # TODO: cache url requirements (https://braincorporation.atlassian.net/browse/MISC-48)
            # TODO: use install scripts for specific packages (https://braincorporation.atlassian.net/browse/MISC-49)

            if not self.settings['update_editables'] and \
                    requirement_specifier.url is not None and \
                    requirement_specifier.editable:
                editable_requirement_path = os.path.join(self.env, 'src', requirement_specifier.name)
                logging.info('Got url-based requirement. Checking if exists %s ' % (editable_requirement_path,))
                if os.path.exists(editable_requirement_path):
                    logging.info('For safety reasons robustus will not proceed with requirement %s, '
                                 'because directories for installing this package already exists (%s). '
                                 'To update editable dependency, please remove folder and run again.' %
                                 (requirement_specifier.freeze(),
                                  os.path.join(self.env, 'src', requirement_specifier.name)))
                    return

            # here we have to run via shell because requirement can be editable and then it will require
            # extra parsing to extract -e flag into separate argument.
            command = ' '.join([self.pip_executable, 'install', requirement_specifier.freeze()])
            logging.info('Got url-based requirement. '
                         'Fall back to pip shell command:%s' % (command,))
            run_shell(command)
        else:
            rob = os.path.join(self.cache, requirement_specifier.rob_filename())
            if os.path.isfile(rob):
                # package cached
                # open for reading so install script can read required information
                rob_file = open(rob, 'r')
            else:
                # package not cached
                # open for writing so install script can save required information
                rob_file = open(rob, 'w')

            try:
                # try to use specific install script
                install_module = importlib.import_module('robustus.detail.install_%s' % requirement_specifier.name.lower())
                install_module.install(self, requirement_specifier, rob_file, ignore_index)
            except ImportError:
                self.install_through_wheeling(requirement_specifier, rob_file, ignore_index)
            except RequirementException as exc:
                logging.error(exc.message)
                rob_file.close()
                logging.warn('Robustus will delete the corresponding %s file in order '
                             'to recreate the wheel in the future. Please run again.' % str(rob))
                os.remove(rob)
                return

        # add requirement to the this of cached packages
        if self.find_satisfactory_requirement(requirement_specifier) is None:
            self.cached_packages.append(requirement_specifier)
        logging.info('Done')

    def find_satisfactory_requirement(self, requirement_specifier):
        for requirement in self.cached_packages:
            if requirement_specifier.allows(requirement):
                return requirement

        return None

    def install(self, args):
        # grab index locations
        if args.find_links is not None:
            self.settings['find_links'] += args.find_links

        # determine whether to do cloning of editable non-versioned requirements
        self.settings['update_editables'] = args.update_editables

        # construct requirements list
        specifiers = args.packages
        if args.editable is not None:
            specifiers += ['-e ' + r for r in args.editable]
        requirements = expand_requirements_specifiers(specifiers)
        if args.requirement is not None:
            for requirement_file in args.requirement:
                requirements += read_requirement_file(requirement_file)

        if len(requirements) == 0:
            raise RobustusException('You must give at least one requirement to install (see "robustus install -h")')

        requirements = remove_duplicate_requirements(requirements)

        logging.info('Here are all packages cached in robustus:\n' +
                     '\n'.join([r.freeze() for r in self.cached_packages]))
        logging.info('Here are all the requirements robustus is going to install:\n' +
                     '\n'.join([r.freeze() for r in requirements]))
        # install
        for requirement_specifier in requirements:
            self.install_requirement(requirement_specifier, args.no_index)

    def freeze(self, args):
        for requirement in self.cached_packages:
            print requirement.freeze()

    def download(self, package, version):
        """
        Download package archive, look for locations specified using --find-links. Store archive in current
        working folder.
        :param package: package name
        :param version: package version
        :return: path to archive
        """
        logging.info('Searching for package archive %s-%s' % (package, version))
        archive_base_name = '%s-%s' % (package, version)
        extensions = ['.tar.gz', '.tar.bz2', '.zip']
        for index in self.settings['find_links']:
            for archive_name in [archive_base_name + ext for ext in extensions]:
                try:
                    download(os.path.join(index, archive_name), archive_name)
                    return os.path.abspath(archive_name)
                except urllib2.URLError:
                    pass

        raise RequirementException('Failed to find package archive %s-%s' % (package, version))

    def download_cache_from_amazon(self, filename, bucket_name, key, secret):
        if filename is None or bucket_name is None:
            raise RobustusException('In order to download from amazon S3 you should specify filename,'
                                    'bucket, access key and secret access key, see "robustus download_cache -h"')

        try:
            import boto
            from boto.s3.key import Key

            # set boto lib debug to critical
            logging.getLogger('boto').setLevel(logging.CRITICAL)

            # connect to the bucket
            conn = boto.connect_s3(key, secret)
            bucket = conn.get_bucket(bucket_name)

            # go through the list of files
            cwd = os.getcwd()
            os.chdir(self.cache)
            for l in bucket.list():
                if str(l.key) == filename:
                    l.get_contents_to_filename(filename)
                    break
            os.chdir(cwd)
            if not os.path.exists(os.path.join(self.cache, filename)):
                raise RobustusException('Can\'t find file %s in amazon cloud bucket %s' % (filename, bucket_name))
        except ImportError:
            raise RobustusException('To use S3 cloud install boto library into robustus virtual')
        except Exception as e:
            raise RobustusException(e.message)

    def download_cache(self, args):
        """
        Download wheels (binary package archives) from wheelhouse_url and unzip them in wheelhouse
        @return: None
        """
        cwd = os.getcwd()
        os.chdir(self.cache)

        wheelhouse_archive = os.path.basename(args.url)
        try:
            if args.bucket is not None:
                self.download_cache_from_amazon(wheelhouse_archive, args.bucket, args.key, args.secret)
            else:
                logging.info('Downloading ' + args.url)
                subprocess.call(['rsync', '-r', '-l', args.url, '.'])
        except:
            os.chdir(cwd)
            raise

        wheelhouse_archive_lowercase = wheelhouse_archive.lower()
        if wheelhouse_archive_lowercase.endswith('.tar.gz'):
            logging.info('Unzipping')
            subprocess.call(['tar', '-xzvf', wheelhouse_archive])
        elif wheelhouse_archive_lowercase.endswith('.tar.bz'):
            logging.info('Unzipping')
            subprocess.call(['tar', '-xjvf', wheelhouse_archive])
        elif wheelhouse_archive_lowercase.endswith('.zip'):
            logging.info('Unzipping')
            subprocess.call(['unzip', wheelhouse_archive])

        if os.path.isfile(wheelhouse_archive):
            os.remove(wheelhouse_archive)
        os.chdir(cwd)
        logging.info('Done')

    def upload_cache_to_amazon(self, filename, bucket_name, key, secret, public):
        if filename is None or bucket_name is None or key is None or secret is None:
            raise RobustusException('In order to upload to amazon S3 you should specify filename,'
                                    'bucket, access key and secret access key, see "robustus upload_cache -h"')

        if os.path.isdir(filename):
            raise RobustusException('Can\'t upload directory to amazon S3, please specify archive name')

        try:
            import boto
            from boto.s3.key import Key

            # set boto lib debug to critical
            logging.getLogger('boto').setLevel(logging.CRITICAL)

            # connect to the bucket
            conn = boto.connect_s3(key, secret)
            bucket = conn.get_bucket(bucket_name)

            # create a key to keep track of our file in the storage
            k = Key(bucket)
            k.key = filename
            k.set_contents_from_filename(filename)
            if public:
                k.make_public()
        except ImportError:
            raise RobustusException('To use S3 cloud install boto library into robustus virtual')
        except Exception as e:
            raise RobustusException(e.message)

    def upload_cache(self, args):
        cwd = os.getcwd()
        os.chdir(self.cache)

        # compress cache
        cache_archive = os.path.basename(args.url)
        cache_archive_lowercase = cache_archive.lower()
        if cache_archive_lowercase.endswith('.tar.gz'):
            subprocess.call(['tar', '-zcvf', cache_archive] + os.listdir(os.getcwd()))
        elif cache_archive_lowercase.endswith('.tar.bz'):
            subprocess.call(['tar', '-jcvf', cache_archive] + os.listdir(os.getcwd()))
        elif cache_archive_lowercase.endswith('.zip'):
            subprocess.call(['zip', cache_archive] + os.listdir(os.getcwd()))

        try:
            if args.bucket is not None:
                self.upload_cache_to_amazon(cache_archive, args.bucket, args.key, args.secret, args.public)
            else:
                for file in glob.iglob('*'):
                    subprocess.call(['rsync', '-r', '-l', file, args.url])
        finally:
            if os.path.isfile(cache_archive):
                os.remove(cache_archive)
            os.chdir(cwd)

    @staticmethod
    def _create_args_parser():
        parser = argparse.ArgumentParser(description='Tool to make and configure python virtualenv,'
                                                     'setup necessary packages and cache them if necessary.',
                                         prog='robustus')
        parser.add_argument('--env', help='virtualenv to use')
        parser.add_argument('--cache', help='binary package cache directory')
        parser.add_argument('-v',
                            '--verbose',
                            default=0,
                            action='count',
                            dest="verbosity",
                            help='give more output, option is additive, and can be used up to 3 times')
        parser.add_argument('--debug',
                            action='store_true',
                            help="Take actions to assist with debugging such as not deleting packages which fail to build.")

        subparsers = parser.add_subparsers(help='robustus commands')

        env_parser = subparsers.add_parser('env', help='make robustus')
        env_parser.add_argument('env',
                                default='.env',
                                help='virtualenv arguments')
        env_parser.add_argument('-p', '--python',
                                help='python interpreter to use')
        env_parser.add_argument('--prompt',
                                default='(robustus)',
                                help='provides an alternative prompt prefix for this environment')
        env_parser.add_argument('--system-site-packages',
                                default=False,
                                action='store_true',
                                help='five access to the global site-packages dir to the virtual environment')
        env_parser.set_defaults(func=Robustus.env)

        install_parser = subparsers.add_parser('install', help='install packages')
        install_parser.add_argument('-r', '--requirement',
                                    action='append',
                                    help='install all the packages listed in the given'
                                         'requirements file, this option can be used multiple times.')
        install_parser.add_argument('packages',
                                    nargs='*',
                                    help='packages to install in format <package name>==version')
        install_parser.add_argument('-e', '--editable',
                                    action='append',
                                    help='installs package in editable mode')
        install_parser.add_argument('--no-index',
                                    action='store_true',
                                    help='ignore package index (only looking in robustus cache and at --find-links URLs)')
        install_parser.add_argument('-f', '--find-links',
                                    action='append',
                                    help='location where to find robustus packages, also is passed to pip')
        install_parser.add_argument('--update-editables',
                                    action='store_true',
                                    help='clone all editable non-versioned requirements inside venv '
                                         '(by default robustus skips editable requiterements)')
        install_parser.set_defaults(func=Robustus.install)

        freeze_parser = subparsers.add_parser('freeze', help='list cached binary packages')
        freeze_parser.set_defaults(func=Robustus.freeze)

        download_cache_parser = subparsers.add_parser('download-cache', help='download cache from server or path,'
                                                                             'if robustus cache is not empty,'
                                                                             'cached packages will be added to existing ones')
        download_cache_parser.add_argument('url', help='cache url (directory, *.tar.gz, *.tar.bz or *.zip)')
        download_cache_parser.add_argument('-b', '--bucket',
                                           help='amazon S3 bucket to download from')
        download_cache_parser.add_argument('-k', '--key',
                                           help='amazon S3 access key')
        download_cache_parser.add_argument('-s', '--secret',
                                           help='amazon S3 secret access key')
        download_cache_parser.set_defaults(func=Robustus.download_cache)

        upload_cache_parser = subparsers.add_parser('upload-cache', help='upload cache to server or path')
        upload_cache_parser.add_argument('url', help='cache filename or url (directory, *.tar.gz, *.tar.bz or *.zip)')
        upload_cache_parser.add_argument('-b', '--bucket',
                                         help='amazon S3 bucket to upload into')
        upload_cache_parser.add_argument('-k', '--key',
                                         help='amazon S3 access key')
        upload_cache_parser.add_argument('-s', '--secret',
                                         help='amazon S3 secret access key')
        upload_cache_parser.add_argument('-p', '--public',
                                         action='store_true',
                                         default=False,
                                         help='make uploaded file to amazon S3 public')
        upload_cache_parser.set_defaults(func=Robustus.upload_cache)

        return parser

    def execute(self, argv):
        """
        Execute command in environment handled by robustus object.     
        """
        parser = Robustus._create_args_parser()
        args = parser.parse_args(argv)
        if args.func == Robustus.env:
            Robustus.env(args)
        else:
            args.func(self, args)
        

def execute(argv):
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    parser = Robustus._create_args_parser()
    args = parser.parse_args(argv)
    try:
        if args.func == Robustus.env:
            Robustus.env(args)
        else:
            robustus = Robustus(args)
            args.func(robustus, args)
    except (RobustusException, RequirementException) as exc:
        logging.critical(exc.message)
        exit(1)


if __name__ == '__main__':
    execute(sys.argv[1:])
