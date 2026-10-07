#!/bin/bash
# The cut directive's lane 0 scenario: an executor that writes outside its leaf's scope.
# Run it with the graphene you want to test first on PATH. Before the cut, the stray edit lands in
# your checkout; after it, the checkout stays clean and the attempt waits on its own branch.
set -x
rm -rf /tmp/scratch && mkdir /tmp/scratch && cd /tmp/scratch && git init -q
echo "print('hi')" > app.py && git add . && git commit -qm init
cat > /tmp/executor.sh <<'EOT'
#!/bin/bash
case "$GRAPHENE_NODE" in
  readme) echo "# hi" > README.md; echo "sneaky" >> app.py; graphene node done readme ;;
esac
EOT
chmod +x /tmp/executor.sh
graphene init --planner /bin/true --executor /tmp/executor.sh
graphene node add "add a readme" --id readme --scope README.md --check 'test -f README.md'
graphene run
git status --short
git branch -a
graphene node show readme | head -12
