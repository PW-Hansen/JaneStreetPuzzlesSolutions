## Reflections on this project
This was the fifth project in this manner, and I admittedly did not have a broader goal in mind when I decided to tackle this puzzle, but did so because I usually find the process enjoyable.

Here, however, I learned the hazards of including the full rules for Codex: namely, that it will sometimes include functionality that follows from the rules, rather than because it was requested. In this case, the rules require that the pentominoes placed in the puzzle form a contiguous region, and using that rule is required to reach a unique solution. However, Codex automatically applied this check before it became relevant, without being instructed to do so. 

While it could potentially be interesting to just give Codex the rules and the initial state for a Jane Street puzzle at some point and see how it does, that is not what I am currently experimenting with.

As such, I added the following to the AGENTS.md file that I've been carrying between projects.

"Do not add functionality without being explicitly asked to do so. Even if a rule that has been shared through e.g. docs/rules.md could be incorporated into the current query, refrain from doing so unless prompted. If a prompt would run contrary to a rule, bring this up and ask for clarification, but do not just unilaterally do "the right thing" instead of what was requested."