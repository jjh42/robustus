# =============================================================================
# COPYRIGHT 2013 Brain Corporation.
# License under MIT license (see LICENSE file)
# =============================================================================


import doctest
import robustus
import pytest
import mock
import tempfile
import os


#FIXME: use from robustus.detail.requirement import ...
do_requirement_recursion = robustus.detail.requirement.do_requirement_recursion
RequirementSpecifier = robustus.detail.requirement.RequirementSpecifier
RequirementException = robustus.detail.requirement.RequirementException
remove_duplicate_requirements = robustus.detail.requirement.remove_duplicate_requirements
expand_requirements_specifiers = robustus.detail.requirement.expand_requirements_specifiers
_filter_requirements_lines = robustus.detail.requirement._filter_requirements_lines


def test_requirement_recursion_single_item():
    mock_git = mock.MagicMock()
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(specifier='  -e    numpy == 1.7.2  # comment'))
    assert(not mock_git.called)
    assert(len(reqs) == 1)
 
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(specifier='git+ssh://git@github.com/company/my_package#egg=my_package'))
    assert(not mock_git.called)
    assert(len(reqs) == 1)
    assert(reqs[0].freeze() == 'git+ssh://git@github.com/company/my_package#egg=my_package')
 
    with pytest.raises(RequirementException):
        do_requirement_recursion(mock_git, RequirementSpecifier(specifier='-e git+https://github.com/company/my_package@branch_name'))
 
 
def test_requirement_recursion_single_retreive():
    mock_git = mock.MagicMock()
    mock_git.access.return_value = ['numpy==1', 'scipy==2']
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(
        specifier='-e git+ssh://git@github.com/company/my_package@branch_name#egg=my_package'))
    mock_git.access.assert_called_with('ssh://git@github.com/company/my_package',
                                       'branch_name', 'requirements.txt',
                                       ignore_missing_refs = False)
    assert(len(reqs) == 3)
    assert(reqs[0].freeze() == 'numpy==1')
    assert(reqs[1].freeze() == 'scipy==2')
    assert(reqs[2].freeze() == '-e git+ssh://git@github.com/company/my_package@branch_name#egg=my_package')
 
 
def test_requirement_recursion_two_levels():
 
    class MockGit(object):
        def access(self, link, branch, path, ignore_missing_refs = False):
            assert(path == 'requirements.txt')
            assert(link == 'https://github.com/company/my_package' or 
                   link == 'ssh://git@github.com/company/my_package')
            if branch == 'branch_name':
                return ['numpy==1', 
                        '-e git+ssh://git@github.com/company/my_package@another_branch#egg=my_package', 
                        'scipy==2']
            elif branch == 'another_branch':
                return ['numpy==1', 
                        'opencv==5']
            else:
                raise Exception('Unknown branch name %s' % branch)
 
    mock_git = MockGit()
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(
        specifier='-e git+https://github.com/company/my_package@branch_name#egg=my_package'))
    assert(len(reqs) == 5)
    assert(reqs[0].freeze() == 'numpy==1')
    assert(reqs[1].freeze() == 'opencv==5')
    assert(reqs[2].freeze() == '-e git+ssh://git@github.com/company/my_package@another_branch#egg=my_package')
    assert(reqs[3].freeze() == 'scipy==2')
    assert(reqs[4].freeze() == '-e git+https://github.com/company/my_package@branch_name#egg=my_package')
     
 
def test_remove_requirements_duplicates():
    req_list = [RequirementSpecifier(specifier='numpy == 1.7.2  # comment'),
                RequirementSpecifier(specifier='pytest==2'),
                RequirementSpecifier(specifier='-e git+https://github.com/company/my_package@branch_name#egg=my_package'),
                RequirementSpecifier(specifier='pytest==3'),
                RequirementSpecifier(specifier='-e git+https://github.com/company/my_package@branch_name#egg=my_package'),
                RequirementSpecifier(specifier='pytest==2'),
                RequirementSpecifier(specifier='numpy == 1.7.2  # comment'),
                RequirementSpecifier(specifier='numpy == 1.7.2  # comment'),
                RequirementSpecifier(specifier='git+https://github.com/company/my_package@branch_name#egg=my_package'),
                RequirementSpecifier(specifier='-e git+https://github.com/company/my_package@branch_name#egg=my_package'),
                RequirementSpecifier(specifier='pytest==2'),
                RequirementSpecifier(specifier='numpy==1.7.2'),
                RequirementSpecifier(specifier='-e git+https://github.com/company/my_package@master#egg=my_package'),
                RequirementSpecifier(specifier='numpy==1.7.3')]
                 
    sparse_list = remove_duplicate_requirements(req_list)
    assert(len(sparse_list) == 3)
 
    assert(sparse_list[0].freeze() == 'numpy==1.7.3')
    assert(sparse_list[1].freeze() == 'pytest==2')
    assert(sparse_list[2].freeze() == '-e git+https://github.com/company/my_package@master#egg=my_package')


def test_remove_requirements_duplicates_with_ros_overlays():
    req_list = [RequirementSpecifier(specifier='numpy == 1.7.2  # comment'),
                RequirementSpecifier(specifier='numpy==1.7.2'),
                RequirementSpecifier(specifier='ros_overlay==https://github.com/ros/robot_model.git'),
                RequirementSpecifier(specifier='ros_overlay==https://github.com/ros/robot_model2.git'),
                RequirementSpecifier(specifier='numpy==1.7.3')]
                 
    sparse_list = remove_duplicate_requirements(req_list)
    assert(len(sparse_list) == 3)
 
    assert(sparse_list[0].freeze() == 'numpy==1.7.3')
    assert(sparse_list[1].freeze() == 'ros_overlay==https://github.com/ros/robot_model.git')
    assert(sparse_list[2].freeze() == 'ros_overlay==https://github.com/ros/robot_model2.git')

 
def test_requirement_recursion_starting_with_local_non_editable(tmpdir):
    temp_folder = str(tmpdir.mkdtemp())
    with open(os.path.join(temp_folder, 'requirements.txt'), 'w') as f:
        f.write('-e git+https://github.com/company/my_package@branch_name#egg=my_package\n'
                'opencv=1\n')
 
    reqs = do_requirement_recursion(None, RequirementSpecifier(specifier=temp_folder))
    assert(len(reqs) == 1)
    assert(reqs[0].freeze() == temp_folder)
 
 
def test_requirement_recursion_starting_with_local(tmpdir):
    mock_git = mock.MagicMock()
    mock_git.access.return_value = ['numpy==1', 'scipy==2']
 
    temp_folder = str(tmpdir.mkdtemp())
    with open(os.path.join(temp_folder, 'requirements.txt'), 'w') as f:
        f.write('-e git+https://github.com/company/my_package@branch_name#egg=my_package\n'
                'opencv==1\n')
 
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(specifier='-e ' + temp_folder))
    assert(len(reqs) == 5)
    assert(reqs[0].freeze() == 'numpy==1')
    assert(reqs[1].freeze() == 'scipy==2')
    assert(reqs[2].freeze() == '-e git+https://github.com/company/my_package@branch_name#egg=my_package')
    assert(reqs[3].freeze() == 'opencv==1')
    assert(reqs[4].freeze() == '-e ' + temp_folder)


def test_local_requirement_with_tag_override(tmpdir):
    mock_git = mock.MagicMock()
    mock_git.access.return_value = ['numpy==1', 'scipy==2']
 
    temp_folder = str(tmpdir.mkdtemp())
    with open(os.path.join(temp_folder, 'requirements.txt'), 'w') as f:
        f.write('\n')
 
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(specifier='-e ' + temp_folder))
    reqs[0].override_branch('foo')

 
def test_expand_empty_requirements(tmpdir):
    mock_git = mock.MagicMock()
    result = expand_requirements_specifiers([], mock_git)
    assert(result == [])
 
 
def test_requirement_recursion_do_not_fetch_twice():
 
    class MockGit(object):
        def __init__(self):
            self._traverse_to_internal_count = 0
 
        def access(self, link, branch, path, ignore_missing_refs = False):
            assert(path == 'requirements.txt')
            assert(branch == 'master')
            if link == 'https://github.com/company/my_package':
                return ['-e git+https://github.com/company/my_package2@master#egg=my_package2',
                        '-e git+https://github.com/company/my_package3@master#egg=my_package3']
            elif link == 'https://github.com/company/my_package2':
                return ['-e git+https://github.com/company/inernal_package@master#egg=inernal_package']
            elif link == 'https://github.com/company/my_package3':
                return ['-e git+https://github.com/company/inernal_package@master#egg=inernal_package']
            elif link == 'https://github.com/company/inernal_package':
                self._traverse_to_internal_count += 1
                return ['numpy==1']
            else:
                raise Exception('Unknown path name %s' % link)
 
    mock_git = MockGit()
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(
        specifier='-e git+https://github.com/company/my_package@master#egg=my_package'))
    assert(len(reqs) == 5)
    assert(reqs[0].freeze() == 'numpy==1')
    assert(reqs[1].freeze() == '-e git+https://github.com/company/inernal_package@master#egg=inernal_package')
    assert(reqs[2].freeze() == '-e git+https://github.com/company/my_package2@master#egg=my_package2')
    assert(reqs[3].freeze() == '-e git+https://github.com/company/my_package3@master#egg=my_package3')
    assert(reqs[4].freeze() == '-e git+https://github.com/company/my_package@master#egg=my_package')
 
    assert(mock_git._traverse_to_internal_count == 1)


def test_filter_requirements_lines():
    assert(_filter_requirements_lines([
        'aa',
        'bb'
    ]) == [
        'aa',
        'bb'])

    assert(_filter_requirements_lines([
        'aa',
        ''
    ]) == [
        'aa'])

    assert(_filter_requirements_lines([
        'aa',
        'bb',
        'cc'
    ]) == [
        'aa',
        'bb',
        'cc'])

    assert(_filter_requirements_lines([
        '   aa',
        'bb ',
        'cc\t'
    ]) == [
        'aa',
        'bb',
        'cc'])

    assert(_filter_requirements_lines([
        'aa',
        'bba\\',
        'cc'
    ]) == [
        'aa',
        'bbacc'])

    assert(_filter_requirements_lines([
        'aa',
        'bba\\',
        'cc\\'
    ]) == [
        'aa',
        'bbacc'])

    assert(_filter_requirements_lines([
        'aa\\',
        'bba',
        'cc'
    ]) == [
        'aabba',
        'cc'])

    assert(_filter_requirements_lines([
        'aa\\',
        'bba\\',
        'cc'
    ]) == [
        'aabbacc'])

    assert(_filter_requirements_lines([
        'aa\\',
        '\tbba\\',
        '\tcc',
        'dd'
    ]) == [
        'aabbacc',
        'dd'])


def test_multiline_requirements_parsing(tmpdir):
    mock_git = mock.MagicMock()
    mock_git.access.return_value = ['numpy == 1', 'scipy==\t2']
 
    temp_folder = str(tmpdir.mkdtemp())
    with open(os.path.join(temp_folder, 'requirements.txt'), 'w') as f:
        f.write('-e git+https://github.com/company/my_p\\\n  ackage@branch_name#egg=my_package\n'
                'ope\\\n\tncv==1\n')
 
    reqs = do_requirement_recursion(mock_git, RequirementSpecifier(specifier='-e ' + temp_folder))
    assert(len(reqs) == 5)
    assert(reqs[0].freeze() == 'numpy==1')
    assert(reqs[1].freeze() == 'scipy==2')
    assert(reqs[2].freeze() == '-e git+https://github.com/company/my_package@branch_name#egg=my_package')
    assert(reqs[3].freeze() == 'opencv==1')
    assert(reqs[4].freeze() == '-e ' + temp_folder)


def test_doc_tests():
    result = doctest.testmod(robustus.detail.requirement)
    if result[0]>0:
        raise Exception(str(result))

if __name__ == '__main__':
    test_doc_tests()
    pytest.main('-s %s -n0' % __file__)
