# =============================================================================
# COPYRIGHT 2013 Brain Corporation.
# License under MIT license (see LICENSE file)
# =============================================================================

import os
import re
import urlparse
from git_accessor import GitAccessor


class RequirementException(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


class Requirement(object):
    def __init__(self, *args, **kwargs):
        """
        Create requirement.
        @args: name, version
        @kwargs: name, version, url, rob_filename
        Examples:
        >>> Requirement('numpy', '1.7.2')
        Requirement(name='numpy', version='1.7.2')
        >>> Requirement(url='http://requirement.org/requirement.zip')
        Requirement(url='http://requirement.org/requirement.zip')
        >>> Requirement(rob_filename='numpy__1_7_1.rob')
        Requirement(name='numpy', version='1.7.1')
        """
        self.name = kwargs.get('name', None)
        self.version = kwargs.get('version', None)
        self.url = None
        self.editable = kwargs.get('editable', False)
        if 'url' in kwargs:
            self.url = urlparse.urlparse(kwargs['url'])
        if len(args) > 0:
            self.name = args[0]
            if len(args) > 1:
                self.version = args[1]
        if 'specifier' in kwargs:
            self._from_specifier(kwargs['specifier'])
        elif 'rob_filename' in kwargs:
            self._from_rob(kwargs['rob_filename'])

    def _from_rob(self, rob_filename):
        """
        Return package name and version from package rob file name
        @return: (name, version, url, allow_greater_version)
        Examples:
        >>> Requirement()._from_rob('numpy__1_7_2.rob')
        ('numpy', '1.7.2', None)
        >>> Requirement()._from_rob('scipy.rob')
        ('scipy', None, None)
        >>> Requirement()._from_rob('/path/to/somewhere/scipy.rob')
        ('scipy', None, None)
        """
        assert(rob_filename.endswith('.rob'))

        rob_basename = os.path.basename(rob_filename)
        if rob_basename.find('__') != -1:
            self.name, self.version = rob_basename[:-4].split('__')
            self.version = self.version.replace('_', '.')
        else:
            self.name = rob_basename[:-4]
            self.version = None
        self.url = None

        return self.name, self.version, self.url

    def __repr__(self):
        str = 'Requirement('
        if self.name is not None:
            str += 'name=\'%s\'' % self.name
            if self.version is not None:
                str += ', version=\'%s\'' % self.version
        elif self.url is not None:
            str += 'url=\'%s\'' % self.url.geturl()
        str += ')'
        return str

    def freeze(self):
        """
        @return: string representing requirement in pip format with all necessary flags
        Examples:
        >>> Requirement('numpy', '1.7.2').freeze()
        'numpy==1.7.2'
        >>> Requirement('numpy', '1.7.2', editable=True).freeze()
        '-e numpy==1.7.2'
        >>> Requirement(url='http://requirement.org/requirement.zip').freeze()
        'http://requirement.org/requirement.zip'
        >>> Requirement(url='http://requirement.org/requirement.zip', editable=True).freeze()
        '-e http://requirement.org/requirement.zip'
        """
        str = ''
        if self.editable:
            str += '-e '
        return str + self._freeze_base()

    def _freeze_base(self):
        """
        @return: string representing requirement in pip format without flags
        Examples:
        >>> Requirement('numpy', '1.7.2', editable = True)._freeze_base()
        'numpy==1.7.2'
        >>> Requirement('numpy', '1.7.2', editable = False)._freeze_base()
        'numpy==1.7.2'
        >>> Requirement(url='http://requirement.org/requirement.zip')._freeze_base()
        'http://requirement.org/requirement.zip'
        """
        if self.url is not None:
            return self.url.geturl()
        else:
            if self.version is not None:
                return '%s==%s' % (self.name, self.version)
            return self.name
        

    def rob_filename(self):
        """
        Get filename to store information about cached package.
        TODO: add support for packages installed via urls.
        @return: filename to store package information <package_name>__<package_version>.rob
        (dots replaced with underscores)
        Examples:
        >>> Requirement('numpy', '1.7.2').rob_filename()
        'numpy__1_7_2.rob'
        >>> Requirement('scipy').rob_filename()
        'scipy.rob'
        """
        if self.name is not None:
            if self.version is not None:
                return '%s__%s.rob' % (self.name, self.version.replace('.', '_'))
            return '%s.rob' % self.name


class RequirementSpecifier(Requirement):
    def __init__(self, *args, **kwargs):
        """
        Create requirement specifier.
        @args: same as in Requirement
        @kwargs: same as in Requirement plus 'specifier', 'allow_greater_version'
        Examples:
        >>> RequirementSpecifier(url='http://requirement.org/requirement.zip')
        RequirementSpecifier(url='http://requirement.org/requirement.zip')
        >>> RequirementSpecifier(specifier='numpy>=1.7.1')
        RequirementSpecifier(name='numpy', version='1.7.1', allow_greater_version)
        >>> RequirementSpecifier(specifier='-e numpy>=1.7.1')
        RequirementSpecifier(name='numpy', version='1.7.1', allow_greater_version, editable)
        """
        Requirement.__init__(self, *args, **kwargs)
        self.allow_greater_version = kwargs.get('allow_greater_version', False)
        if 'specifier' in kwargs:
            self._from_specifier(kwargs['specifier'])

    def _from_specifier(self, specifier):
        """
        Extract requirement name and version from requirement string
        @return: (name, version, url, allow_greater_version, editable)
        Examples:
        >>> RequirementSpecifier()._from_specifier('numpy==1.7.2')
        ('numpy', '1.7.2', None, False, False)
        >>> RequirementSpecifier()._from_specifier('-e numpy==1.7.2')
        ('numpy', '1.7.2', None, False, True)
        >>> RequirementSpecifier()._from_specifier('   numpy == 1.7.2  ')
        ('numpy', '1.7.2', None, False, False)
        >>> RequirementSpecifier()._from_specifier('   numpy >= 1.7.2  ')
        ('numpy', '1.7.2', None, True, False)
        >>> RequirementSpecifier()._from_specifier('   numpy == 1.7.2  # comment')
        ('numpy', '1.7.2', None, False, False)
        >>> RequirementSpecifier()._from_specifier('  -e    numpy == 1.7.2  # comment')
        ('numpy', '1.7.2', None, False, True)
        >>> RequirementSpecifier()._from_specifier('numpy')
        ('numpy', None, None, False, False)
        >>> RequirementSpecifier()._from_specifier('pytest-cache==0.7')
        ('pytest-cache', '0.7', None, False, False)
        >>> RequirementSpecifier()._from_specifier('theano==0.6rc3')
        ('theano', '0.6rc3', None, False, False)
        >>> RequirementSpecifier()._from_specifier('http://some_url/some_package.tar.gz')
        (None, None, 'http://some_url/some_package.tar.gz', False, False)
        >>> RequirementSpecifier()._from_specifier('   http://some_url/some_package.tar.gz')
        (None, None, 'http://some_url/some_package.tar.gz', False, False)
        >>> RequirementSpecifier()._from_specifier('-e   http://some_url/some_package.tar.gz')
        (None, None, 'http://some_url/some_package.tar.gz', False, True)
        >>> RequirementSpecifier()._from_specifier('-e git+https://github.com/company/my_package@branch_name#egg=my_package')
        (None, None, 'git+https://github.com/company/my_package@branch_name#egg=my_package', False, True)
        >>> RequirementSpecifier()._from_specifier('numpy==1.7.2==1.7.2')
        Traceback (most recent call last):
            ...
        RequirementException: invalid requirement specified "numpy==1.7.2==1.7.2"
        >>> RequirementSpecifier()._from_specifier('   ')
        Traceback (most recent call last):
            ...
        RequirementException: invalid requirement specified ""
        >>> RequirementSpecifier()._from_specifier('numpy==')
        Traceback (most recent call last):
            ...
        RequirementException: invalid requirement specified "numpy=="
        """
        self.name = None
        self.version = None
        self.allow_greater_version = False
        self.editable = False

        specifier = specifier.lstrip()
        if specifier.startswith('-e'):
            self.editable = True
            specifier = specifier[2:].lstrip()
        # check if requirement is url
        self.url = urlparse.urlparse(specifier)
        if len(self.url.scheme) == 0:
            self.url = None
            # check if requirement is in <package>[==|>=]<version> format
            mo = re.match(r'^([\w-]+)\s*(?:([>=]=)?\s*([\w.]+))?\s*(?:#.*)?$', specifier)
            if mo is None:
                raise RequirementException('invalid requirement specified "%s"' % specifier)
            self.name, self.version = mo.group(1, 3)
            # check if user accepts greater version, i.e. >= is used
            version_specifier = mo.group(2)
            if version_specifier is not None and version_specifier == '>=':
                self.allow_greater_version = True

        url = None if self.url is None else self.url.geturl()
        return self.name, self.version, url, self.allow_greater_version, self.editable

    def __repr__(self):
        str = Requirement.__repr__(self).replace('Requirement', 'RequirementSpecifier')[:-1]
        if self.allow_greater_version:
            if len(str) >= len('RequirementSpecifier('):
                str += ', '
            str += 'allow_greater_version'
        if self.editable:
            str += ', editable'
        str += ')'
        return str

    def allows(self, other):
        """
        Check if this requirement specifier allows to install specified requirement.
        I.e. it has same name and version or downloaded from same url.
        @other: requirement
        Examples:
        >>> RequirementSpecifier('numpy', '1.7.2').allows(Requirement('numpy', '1.7.2'))
        True
        >>> RequirementSpecifier('numpy').allows(Requirement('numpy', '1.7.2'))
        True
        >>> RequirementSpecifier('numpy', '1.7.2').allows(Requirement('numpy'))
        False
        >>> RequirementSpecifier(url='http://req.org/req.zip').allows(Requirement(url='http://req.org/req.zip'))
        True
        """
        if self.url is not None and other.url is not None:
            # downloaded from same url
            return self.url == other.url
        elif self.name is not None and other.name is not None:
            # check if name and version match
            # TODO: check for allow_greater_version, note that version can have weird format, i.e. '1.1rc3'
            return self.version is None or other.version == self.version
        else:
            return False


def do_requirement_recursion(git_accessor, original_req):
    '''
    Recursive extraction of requirements from -e git+.. pip links.
    @return: list
    '''
    if not original_req.editable or original_req.url is None:
        return [original_req]

    if not original_req.url.geturl().startswith('git+'):
        return [original_req]

    url = original_req.url.geturl()[4:]
    egg_position = url.find('#egg')
    if egg_position < 0:
        raise RequirementException(
            'Editable git link %s has to contain egg information.'
            'Example: -e git+https://github.com/company/my_package@branch_name#egg=my_package' % 
            original_req.url.geturl())
    url = url[:egg_position]

    if url.startswith('ssh://git@'):
        # searching '@' after git@
        at_pos = url.find('@', 11) 
    else:
        at_pos = url.find('@')

    if at_pos > 0:
        link, tag = url[:at_pos], url[at_pos+1:]
    else:
        link, tag = url, None

    req_file_content = git_accessor.access(link, tag, 'requirements.txt')
    if req_file_content is None:
        raise RequirementException('Editable requirement %s does not have a requirements.txt file')

    requirements = []
    for line in req_file_content:
        if line[0] == '#' or line.isspace() or (len(line) < 2):
            continue
        r = RequirementSpecifier(specifier=line)
        requirements += do_requirement_recursion(git_accessor, r)
    return requirements + [original_req]


def read_requirement_file(requirement_file):
    '''
    Nice dirty hack to test the workflow:)
    In order to process hierarchical dependencies, we assume that -e git+ links
    may contain another requirements.txt file that we will include.
    
    Another way of doing that is to have dependencies only in setup.py and
    run 'python setup.py egg_info" for each package and analyse results
    (this is what pip does to process all dependencies in pip).
    However we loosing wheeling capability - robustus will never get control
    back if pip started to process dependencies from egg_info.
    '''
    requirements = []
    git_accessor = GitAccessor()
    for line in open(requirement_file, 'r'):
        if line[0] == '#' or line.isspace() or (len(line) < 2):
            continue
        r = RequirementSpecifier(specifier=line)
        requirements += do_requirement_recursion(git_accessor, r)

    return requirements