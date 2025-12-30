#!/usr/bin/env python3
"""Interactive program that asks the user to double a random number."""

import random

def main():
    number = random.randint(1, 99)
    print(f"What is {number} doubled?")
    user_input = input()
    try:
        answer = int(user_input)
        if answer == number * 2:
            print("Correct!")
        else:
            print(f"Wrong! The answer was {number * 2}")
    except ValueError:
        print("That isn't a number")

if __name__ == "__main__":
    main()
