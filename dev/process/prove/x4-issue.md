print tags in gherkin-terminal-reporter (pytest-bdd issue #476)

Hello, I am using the Gherkin tags in the feature specification to refer scenarios to different software requirements and it would be really convenient to be able to get those tags printed when I run pytest with the `--gherkin-terminal-reporter` option. I know they are generated into the cucumber JSON but that's less human readable as of right now.

The feature looks like this:
```
@R1.1 @R1.2
  Scenario: Send packages to socket
    Given a service listening on a random socket
    When tool sends "2" packages to socket
    Then "2" packages are received in the service
```

So it would be great to get the tags formatted in some way in the output of the test:

```
$ pytest --gherkin-terminal-reporter -vv
===================================================================================== test session starts =====================================================================================

tests/pacsio_test.py::test_send_packages_to_socket <- utilities/pacs_io/.venv/lib/python3.8/site-packages/pytest_bdd/scenario.py
Feature: Tool for network testing
    Scenario: Send packages to socket
    Given a service listening on a random socket
    When tool sends "2" packages to socket
    Then "2" packages are received in the service
    PASSED
    (tags: R1.1, R1.2)
```
