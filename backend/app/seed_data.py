"""Seed content for Second Arrow.

All summaries below are short, original, beginner-friendly study notes —
NOT scripture, NOT professional or medical advice. They are meant as a
starting point for personal practice and further reading.

Ordering of CONCEPTS defines the suggested learning path. "The Second
Arrow" is intentionally first.
"""

# Each concept becomes a row in the `concepts` table. `order_index` is the
# position in the learning path (lower = earlier).
CONCEPTS = [
    {
        "slug": "the-second-arrow",
        "title": "The Second Arrow",
        "summary": "Pain happens. The extra suffering we pile on top is optional.",
        "definition": (
            "A well-known Buddhist teaching uses two arrows. The first arrow is "
            "the unavoidable pain of life: a harsh word, a loss, physical hurt, a "
            "plan that falls apart. The second arrow is everything we add on top of "
            "that pain with our own mind — anger, blame, replaying the story, "
            "resentment, and 'this shouldn't be happening.' The first arrow we often "
            "cannot prevent. The second arrow is the one we can learn to put down."
        ),
        "why_anger": (
            "Most anger is a second arrow. Something real happened (first arrow), and "
            "then the mind builds a case: they always do this, I'm being disrespected, "
            "this is unfair. Seeing the gap between the event and the story we add is "
            "the first real choice point with anger."
        ),
        "practice": (
            "Next time you feel angry, silently name the two arrows. 'First arrow: the "
            "thing that happened.' 'Second arrow: the story I'm adding.' You don't have "
            "to fix anything yet — just notice that there are two."
        ),
        "reflection": "What is the first arrow here, and what am I adding on top of it?",
        "tags": ["core", "anger", "suffering"],
        "source_notes": "Inspired by the Sallatha Sutta (the parable of the two arrows). TODO: add citation/link for further reading.",
    },
    {
        "slug": "dukkha",
        "title": "Dukkha (Unsatisfactoriness)",
        "summary": "A built-in sense that things are off, incomplete, or not quite enough.",
        "definition": (
            "Dukkha is often translated as 'suffering,' but it points to something "
            "broader: the friction, stress, and unsatisfactoriness woven through "
            "ordinary experience. It ranges from obvious pain to a quiet background "
            "feeling that this moment should be different than it is."
        ),
        "why_anger": (
            "Anger frequently grows out of dukkha — the gap between how things are and "
            "how we wanted them to be. Recognizing that some friction is simply part of "
            "being alive can soften the demand that reality behave exactly as we wish."
        ),
        "practice": (
            "When irritation appears, pause and note: 'This is dukkha — a moment of "
            "things not matching my wish.' Naming it can create a little space around it."
        ),
        "reflection": "Where am I expecting this moment to be different than it is?",
        "tags": ["core", "foundations", "suffering"],
        "source_notes": "Central theme of the First Noble Truth. TODO: add beginner-friendly source.",
    },
    {
        "slug": "craving-and-aversion",
        "title": "Craving and Aversion",
        "summary": "The pull toward what we want and the push against what we don't.",
        "definition": (
            "Much of our reactivity comes down to two movements of mind: craving "
            "(wanting to grab, keep, or get more) and aversion (wanting to push away, "
            "avoid, or destroy). They feel automatic, but they can be noticed."
        ),
        "why_anger": (
            "Anger is a form of aversion — the mind shoving against something it doesn't "
            "want. Seeing anger as 'aversion arising' makes it a little less personal and "
            "a little easier to observe instead of obey."
        ),
        "practice": (
            "When anger shows up, label it lightly: 'aversion.' Notice the urge to push "
            "away. You can feel the urge without acting on it."
        ),
        "reflection": "What am I trying to push away right now?",
        "tags": ["foundations", "anger", "mind"],
        "source_notes": "Relates to the Second Noble Truth (the origin of dukkha in craving). TODO: add source.",
    },
    {
        "slug": "impermanence",
        "title": "Impermanence (Anicca)",
        "summary": "Everything changes — including this feeling, including this anger.",
        "definition": (
            "Anicca is the observation that all experiences arise and pass: thoughts, "
            "moods, sensations, situations. Nothing stays fixed, even the states that "
            "feel overwhelming in the moment."
        ),
        "why_anger": (
            "Anger feels permanent and total while it's happening. Remembering that it is "
            "a wave that will crest and fall makes it easier to wait it out rather than "
            "act from its peak."
        ),
        "practice": (
            "When anger rises, watch it like weather. Notice it building, holding, and "
            "easing. You don't have to make it leave — just witness that it moves."
        ),
        "reflection": "If I know this feeling will pass, how much do I need to act on it right now?",
        "tags": ["foundations", "anger", "mind"],
        "source_notes": "One of the three marks of existence. TODO: add source.",
    },
    {
        "slug": "non-attachment",
        "title": "Non-attachment",
        "summary": "Holding things with an open hand instead of a clenched fist.",
        "definition": (
            "Non-attachment is not coldness or not caring. It is caring without needing "
            "to grip — being able to engage fully while staying willing to let outcomes, "
            "opinions, and even being right not go your way."
        ),
        "why_anger": (
            "A lot of anger is attachment to being right, to control, or to a particular "
            "outcome. Loosening that grip removes much of the fuel before the fire spreads."
        ),
        "practice": (
            "In a tense moment, ask: 'What am I gripping here?' See if you can hold your "
            "position a little more loosely — open hand, not clenched fist."
        ),
        "reflection": "What am I gripping that I could hold more lightly?",
        "tags": ["practice", "anger", "mind"],
        "source_notes": "TODO: add beginner-friendly source on non-attachment vs. detachment.",
    },
    {
        "slug": "mindfulness",
        "title": "Mindfulness (Sati)",
        "summary": "Noticing what's happening, as it happens, without immediately reacting.",
        "definition": (
            "Mindfulness is paying attention to the present moment — body, feelings, "
            "thoughts — with a steady, non-judging awareness. It is the skill that lets "
            "us catch a reaction early, while there is still room to choose."
        ),
        "why_anger": (
            "Anger moves fast. Mindfulness is what notices 'anger is arising' before it "
            "becomes 'I said the thing I regret.' It widens the gap between trigger and "
            "response."
        ),
        "practice": (
            "Try a single mindful breath right now. Feel the air come in, feel it go out. "
            "That one breath is a small rehearsal for noticing before reacting."
        ),
        "reflection": "What am I actually feeling in my body and mind right now?",
        "tags": ["core", "practice", "mind"],
        "source_notes": "Part of the Eightfold Path (Right Mindfulness). TODO: add source.",
    },
    {
        "slug": "right-speech",
        "title": "Right Speech",
        "summary": "Speaking truthfully, kindly, and at the right time — or not at all.",
        "definition": (
            "Right Speech is a guideline for how we communicate: avoiding lying, harsh "
            "words, divisive talk, and idle chatter. A useful filter is: is it true, is "
            "it kind, is it necessary, is it the right time?"
        ),
        "why_anger": (
            "Angry speech is where the second arrow usually escapes into the world and "
            "causes lasting damage. A pause before speaking is often the whole practice."
        ),
        "practice": (
            "Before responding in anger, run the filter: true, kind, necessary, timely? "
            "If it fails any of them, wait."
        ),
        "reflection": "Is what I'm about to say true, kind, necessary, and timely?",
        "tags": ["practice", "anger", "speech"],
        "source_notes": "Part of the Eightfold Path. TODO: add source.",
    },
    {
        "slug": "right-action",
        "title": "Right Action",
        "summary": "Acting in ways that reduce harm — to others and to yourself.",
        "definition": (
            "Right Action is conduct that avoids causing harm and supports wellbeing. "
            "In everyday terms: when you're not sure what to do, lean toward the option "
            "that causes the least harm and that you'd respect later."
        ),
        "why_anger": (
            "Anger pushes for action — often action we regret. Pausing to ask 'what is "
            "the least harmful next step?' keeps a hot moment from creating long-term damage."
        ),
        "practice": (
            "In a charged moment, name one action that reduces harm (even if it's just "
            "'do nothing for now') and choose that one."
        ),
        "reflection": "What action here would I still respect tomorrow?",
        "tags": ["practice", "anger", "ethics"],
        "source_notes": "Part of the Eightfold Path. TODO: add source.",
    },
    {
        "slug": "loving-kindness",
        "title": "Loving-kindness (Metta)",
        "summary": "A warm, friendly wish for wellbeing — starting with yourself.",
        "definition": (
            "Metta is the practice of actively wishing wellbeing for yourself and others. "
            "It is trained, not forced — usually through simple repeated phrases like "
            "'may you be safe, may you be at ease.'"
        ),
        "why_anger": (
            "Metta is a direct counter to ill-will. Even briefly wishing the person you're "
            "angry at some basic wellbeing can loosen the grip of hostility — not by "
            "pretending nothing happened, but by softening your own state."
        ),
        "practice": (
            "Silently offer one phrase to yourself ('may I be at ease') and one to the "
            "other person ('may you be at ease'). Notice any resistance without judging it."
        ),
        "reflection": "Can I wish this person basic wellbeing, even while disagreeing with them?",
        "tags": ["practice", "compassion", "anger"],
        "source_notes": "Metta is a classic concentration and heart practice. TODO: add source.",
    },
    {
        "slug": "compassion",
        "title": "Compassion (Karuna)",
        "summary": "Meeting suffering — yours and others' — with care instead of judgment.",
        "definition": (
            "Karuna is the wish for beings to be free from suffering. It includes "
            "self-compassion: treating your own pain and mistakes with the kindness "
            "you'd offer a friend."
        ),
        "why_anger": (
            "Anger often hides pain underneath. Compassion lets you acknowledge the hurt "
            "without weaponizing it, and recognize that the other person is likely "
            "struggling too."
        ),
        "practice": (
            "Place a hand on your chest and acknowledge: 'this is a hard moment.' Offer "
            "yourself the kindness you'd give a friend in the same spot."
        ),
        "reflection": "What pain might be underneath this anger — mine and theirs?",
        "tags": ["practice", "compassion", "anger"],
        "source_notes": "TODO: add beginner-friendly source on karuna and self-compassion.",
    },
    {
        "slug": "equanimity",
        "title": "Equanimity (Upekkha)",
        "summary": "A steady, balanced mind that doesn't get swept away.",
        "definition": (
            "Equanimity is calm steadiness in the face of ups and downs. It is not "
            "indifference — it's the balance that lets you stay present and caring "
            "without being knocked over by every wave of feeling."
        ),
        "why_anger": (
            "Equanimity is the ground that lets anger arise and pass without hijacking "
            "you. From a steady base you can feel the heat of anger and still choose your "
            "response."
        ),
        "practice": (
            "Feel your feet on the floor or your seat in the chair. Let that physical "
            "steadiness remind you: 'I can feel this and stay standing.'"
        ),
        "reflection": "Can I stay steady and present with this feeling without being swept away?",
        "tags": ["practice", "mind", "anger"],
        "source_notes": "One of the four brahmaviharas. TODO: add source.",
    },
    {
        "slug": "patience",
        "title": "Patience (Kshanti / Khanti)",
        "summary": "The strength to stay steady and not strike back, even when provoked.",
        "definition": (
            "Patience here is not gritted-teeth endurance. It is the trained capacity to "
            "stay open, tolerant, and non-retaliating under difficulty — to give a hard "
            "moment time and space instead of reacting instantly."
        ),
        "why_anger": (
            "Patience is the direct antidote to anger. It is what turns the pause into a "
            "real choice and keeps the second arrow from flying."
        ),
        "practice": (
            "When you feel the push to react now, try waiting through three slow breaths "
            "before doing anything. Treat the delay itself as the practice."
        ),
        "reflection": "What would patience actually look like in this exact situation?",
        "tags": ["core", "practice", "anger"],
        "source_notes": "Kshanti is one of the paramitas (perfections). TODO: add source.",
    },
    {
        "slug": "four-noble-truths",
        "title": "The Four Noble Truths",
        "summary": "A simple map: there is suffering, it has a cause, it can ease, and there's a path.",
        "definition": (
            "A foundational framework: (1) there is dukkha; (2) dukkha has a cause, "
            "largely craving and aversion; (3) dukkha can ease; (4) there is a path of "
            "practice that leads there. Think of it as diagnosis, cause, prognosis, and "
            "treatment."
        ),
        "why_anger": (
            "Applied to anger: anger hurts (1), it has causes like clinging and aversion "
            "(2), it can lessen (3), and there are concrete practices that help (4). It "
            "reframes anger as workable rather than as just who you are."
        ),
        "practice": (
            "Pick one recent flash of anger and walk it through the four steps: the hurt, "
            "the craving/aversion behind it, the possibility of ease, one practice to try."
        ),
        "reflection": "What craving or aversion is sitting underneath this anger?",
        "tags": ["core", "foundations"],
        "source_notes": "The Buddha's first teaching. TODO: add source.",
    },
    {
        "slug": "eightfold-path",
        "title": "The Eightfold Path",
        "summary": "Eight everyday areas of practice that support a calmer, wiser life.",
        "definition": (
            "The fourth Noble Truth spelled out: right view, intention, speech, action, "
            "livelihood, effort, mindfulness, and concentration. It's less a checklist "
            "and more a set of mutually supporting habits of mind and behavior."
        ),
        "why_anger": (
            "Several factors speak directly to anger — right speech, right action, right "
            "mindfulness, right effort. Together they give a practical toolkit for "
            "responding skillfully instead of reacting."
        ),
        "practice": (
            "Choose one factor (say, right speech) and make it your focus for a single "
            "day. Notice what you learn about your own reactivity."
        ),
        "reflection": "Which part of the path would help most with my anger right now?",
        "tags": ["core", "foundations", "ethics"],
        "source_notes": "The fourth Noble Truth. TODO: add source.",
    },
    {
        "slug": "watching-anger-arise-and-pass",
        "title": "Watching Anger Arise and Pass",
        "summary": "Observing anger as an event in the body and mind rather than a command.",
        "definition": (
            "This is mindfulness applied directly to anger: noticing the first signs "
            "(heat, tension, a tightening story), staying with the experience, and "
            "watching it build and fade without acting it out."
        ),
        "why_anger": (
            "When you can observe anger instead of being it, you get your choice back. "
            "The feeling can be fully present and you still decide what to do."
        ),
        "practice": (
            "Next time anger comes, narrate it quietly: 'heat rising… jaw tight… story "
            "forming… now easing.' Be the witness, not just the reactor."
        ),
        "reflection": "Can I watch this anger like an event passing through, rather than become it?",
        "tags": ["core", "practice", "anger"],
        "source_notes": "Applied mindfulness practice. TODO: add source.",
    },
    {
        "slug": "responding-instead-of-reacting",
        "title": "Responding Instead of Reacting",
        "summary": "Using the pause to choose, rather than firing back on autopilot.",
        "definition": (
            "Reacting is automatic and fast; responding is chosen and a beat slower. The "
            "whole point of the pause is to convert a reaction into a response you can "
            "stand behind."
        ),
        "why_anger": (
            "This is the practical heart of Second Arrow: the moment of anger is exactly "
            "where reaction and response split. A little space is all it takes to choose "
            "the second path."
        ),
        "practice": (
            "Build a tiny gap: feel the urge, take one breath, then ask 'what's the "
            "response I'd respect?' Act from the answer, not the urge."
        ),
        "reflection": "Am I reacting on autopilot, or responding from a choice?",
        "tags": ["core", "practice", "anger"],
        "source_notes": "Synthesis of mindfulness and patience practices. TODO: add source.",
    },
]


# Resources are intentionally minimal for the MVP. No invented URLs.
# Add real, verified resources during curation. The structure is here so the
# Resources page and API have something to render and validate against.
RESOURCES = [
    {
        "title": "Find a local meditation or insight (vipassana) group",
        "creator": None,
        "type": "practice",
        "description": (
            "Practicing with others helps. Look for a beginner-friendly meditation or "
            "insight group near you. TODO (curation): add a few vetted directories/links."
        ),
        "url": None,
        "tags": ["beginner", "community", "practice"],
        "beginner_level": True,
        "related_concepts": ["mindfulness", "patience"],
    },
    {
        "title": "Daily metta (loving-kindness) phrases",
        "creator": None,
        "type": "practice",
        "description": (
            "A simple at-home practice: repeat a few well-wishing phrases each morning. "
            "See the Loving-kindness concept for the steps. No external resource needed."
        ),
        "url": None,
        "tags": ["beginner", "metta", "practice"],
        "beginner_level": True,
        "related_concepts": ["loving-kindness", "compassion"],
    },
    # TODO (curation): add real, verified resources here — books, websites,
    # talks, podcasts, channels, articles. Do NOT add invented URLs.
]
