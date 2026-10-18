"""The cockpit: `graphene watch` as a person talking to their agents, in numbers and a few verbs.

It reads the plan's store and draws one row a task with what the agent is doing (files touched of allowed,
proofs, stopped writes, quiet seconds), puts the questions that wait for the person first, and answers
with the commands that exist on their own. Two more screens share its selection: which folders each task
may write (territory), and the plan as boxes and arrows (flow).
"""
