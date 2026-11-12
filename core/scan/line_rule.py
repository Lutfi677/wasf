from core.scan.lines import Line

AVERAGE_MINIMUM = 85.0
WORD_MINIMUM = 50.0


def average(line: Line) -> float:
    words = line["words"]
    return sum(word["confidence"] for word in words) / len(words) if words else 0.0


def lowest(line: Line) -> float:
    return min((word["confidence"] for word in line["words"]), default=0.0)


def goes_to_person(line: Line) -> bool:
    return average(line) < AVERAGE_MINIMUM or lowest(line) < WORD_MINIMUM
