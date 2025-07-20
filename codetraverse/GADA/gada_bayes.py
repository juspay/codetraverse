import json
from itertools import combinations
from collections import defaultdict
from tqdm import tqdm

def create_frequency_tables(commit_data: dict) -> tuple[defaultdict, defaultdict]:
    """
    Analyzes commit data to count function co-occurrence and individual frequency.

    Args:
        commit_data: A dictionary where keys are commit hashes and values are lists of function names.

    Returns:
        A tuple containing two dictionaries:
        - pair_frequencies: Counts for each pair of functions.
        - individual_frequencies: Counts for each individual function.
    """
    pair_frequencies = defaultdict(int)
    individual_frequencies = defaultdict(int)

    # Iterate through each commit's list of functions
    for functions in tqdm(commit_data.values(), desc="calculating frequencies"):
        # Increment frequency for each individual function
        for func in functions:
            individual_frequencies[func] += 1
        
        # Generate all unique pairs of functions within this commit.
        # The key for the pair is sorted to ensure (A, B) is treated the same as (B, A).
        for pair in combinations(functions, 2):
            sorted_pair = str(tuple(sorted(pair)))
            pair_frequencies[sorted_pair] += 1
      
    return pair_frequencies, individual_frequencies


def create_inverted_index(commit_data: dict) -> dict[str, list[str]]:
    """
    Creates an inverted index mapping each function to a list of commit hashes.

    This is a memory-efficient alternative to storing all pair frequencies.

    Args:
        commit_data: A dictionary where keys are commit hashes and values are lists of function names.

    Returns:
        A dictionary where keys are function names and values are lists of commit hashes.
    """
    inverted_index = defaultdict(list)
    
    print("Building inverted index...")
    # Iterate through each commit and its list of functions
    for commit_hash, functions in tqdm(commit_data.items(), desc="Indexing commits"):
        # For each function in the commit, add the commit hash to its list
        for func in functions:
            inverted_index[func].append(commit_hash)
            
    return dict(inverted_index)


def get_joint_frequency_from_index(functions: list[str], inverted_index: dict) -> list:
    """
    Calculates how many times a set of functions appeared together in the same commit.

    Args:
        functions: A list of function names.
        inverted_index: The pre-computed inverted index.

    Returns:
        The co-occurrence frequency count.
    """
    if not functions:
        return []

    # Retrieve the commit lists for the first function
    # Use a set for efficient intersection operations
    try:
        common_commits = set(inverted_index[functions[0]])
    except KeyError:
        # If any function is not in the index, they can't have co-occurred.
        return []

    # Intersect with the commit lists of the remaining functions
    for i in range(1, len(functions)):
        try:
            common_commits.intersection_update(inverted_index[functions[i]])
        except KeyError:
            return []
        # If at any point the intersection is empty, we can stop early
        if not common_commits:
            return []
            
    return list(common_commits)


def find_most_probable_function_from_index(
    conditional_functions: list[str], 
    inverted_index: dict
) -> tuple[list, list]:
    """
    Finds the single most probable next function using the inverted index.
    Calculates P(candidate | conditional_1 AND conditional_2 AND ...).
    """
    # Denominator: How many times did all conditional functions appear together?
    common_commits = get_joint_frequency_from_index(conditional_functions, inverted_index)
    conditional_freq = len(common_commits)

    if conditional_freq == 0:
        print("The given combination of functions never occurred together.")
        return [], common_commits

    best_candidate = None
    max_probability = -1.0
    
    # Get a set of all unique functions available in the index
    all_functions = set(inverted_index.keys())
    candidate_functions = all_functions - set(conditional_functions)
    
    # Iterate through every possible candidate function
    for candidate in candidate_functions:
        # Numerator: How many times did the candidate AND the conditionals appear together?
        joint_freq = len(get_joint_frequency_from_index([candidate] + conditional_functions, inverted_index))
        
        if joint_freq > 0:
            probability = joint_freq / conditional_freq
            if probability > max_probability:
                max_probability = probability
                best_candidate = candidate
                
    if best_candidate is None:
        return [], common_commits

    return [(best_candidate, max_probability)], common_commits

def calculate_path_probability(
    prior_functions: list[str],
    path_to_evaluate: list[str],
    inverted_index: dict
) -> float:
    """
    Calculates the total probability of a specific sequence of functions occurring,
    based on the chain rule of probability: P(A,B|S) = P(A|S) * P(B|S,A).

    Args:
        prior_functions: A list of functions known to be present at the start.
        path_to_evaluate: The sequence of functions whose path probability you want.
        inverted_index: The pre-computed inverted index.

    Returns:
        The total probability of the path occurring.
    """
    # Start with a copy of the priors, so we don't modify the original list
    current_known_functions = list(prior_functions)
    total_path_probability = 1.0
    for next_func_in_path in path_to_evaluate:
        # Denominator: Frequency of the current known functions
        conditional_freq = len(get_joint_frequency_from_index(current_known_functions, inverted_index))

        if conditional_freq == 0:
            print(f"Path broken: The combination {current_known_functions} never occurred.")
            return 0.0

        # Numerator: Frequency of the current known functions PLUS the next function in the path
        joint_freq = len(get_joint_frequency_from_index(current_known_functions + [next_func_in_path], inverted_index))
        # Calculate the conditional probability for this single step
        step_probability = joint_freq / conditional_freq

        # Multiply into the total path probability
        total_path_probability *= step_probability

        # Add the current function to the list of known functions for the next iteration
        current_known_functions.append(next_func_in_path)

    return total_path_probability



def find_next_most_probable_function(
    conditional_functions: list[str], 
    commit_data: dict
) -> tuple[str | None, float]:
    """
    Finds the single most probable next function given a set of existing functions.

    Args:
        conditional_functions: A list of functions known to be present.
        commit_data: The dictionary of commit data.

    Returns:
        A tuple containing the name of the most probable function and its probability.
        Returns (None, 0.0) if no probable function is found.
    """
    # First, get a set of all unique functions in the entire dataset
    all_functions = set(func for funcs_list in commit_data.values() for func in funcs_list)
    
    # Exclude functions that are already in our conditions
    candidate_functions = all_functions - set(conditional_functions)
    
    best_candidate = None
    max_probability = -1.0

    # Iterate through every possible candidate function
    for candidate in candidate_functions:
        # Calculate the probability of this candidate given the conditions
        probability = calculate_joint_conditional_probability(
            candidate, conditional_functions, commit_data
        )
        # If this candidate is better than the best one we've seen so far, update it
        if probability > max_probability:
            max_probability = probability
            best_candidate = candidate
            
    # Handle the case where no co-occurring functions were found
    if best_candidate is None:
        return []

    return [(best_candidate, max_probability)]


def find_most_probable_functions(
    existing_functions: list[str], 
    pair_frequencies: defaultdict, 
    individual_frequencies: defaultdict, 
    top_n: int = 3
) -> list[tuple[str, float]]:
    """
    Finds the most likely functions to appear next based on a list of existing functions.

    Args:
        existing_functions: A list of functions already present.
        pair_frequencies: The frequency table for function pairs.
        individual_frequencies: The frequency table for individual functions.
        top_n: The number of top candidates to return.

    Returns:
        A list of tuples, where each tuple contains a function name and its probability score,
        sorted from most to least likely.
    """
    scores = defaultdict(float)
    all_functions = individual_frequencies.keys()

    # Calculate a probability score for every other function in the dataset
    for candidate_func in tqdm(all_functions, desc="calculating next function"):
        if candidate_func in existing_functions:
            continue  # Skip functions that are already in the input list

        # The score is the sum of conditional probabilities: Σ P(candidate | existing_func)
        total_prob_score = 0
        for existing_func in existing_functions:
            # Conditional probability P(A|B) = Frequency(A,B) / Frequency(B)
            pair_key = tuple(sorted((candidate_func, existing_func)))
            co_occurrence_freq = pair_frequencies.get(str(pair_key), 0)
            
            if individual_frequencies[existing_func] > 0:
                prob = co_occurrence_freq / individual_frequencies[existing_func]
                total_prob_score += prob
        total_prob_score = total_prob_score/len(existing_func)
        if total_prob_score > 0:
            scores[candidate_func] = total_prob_score
    
    # Sort the functions by their calculated score in descending order
    sorted_candidates = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    
    return sorted_candidates[:top_n]



def calculate_joint_conditional_probability(
    target_function: str, 
    conditional_functions: list[str], 
    commit_data: dict
) -> float:
    """
    Calculates the probability of a target function occurring, given that a set of
    other functions have all occurred together in the same commit.
    
    This computes P(target | conditional_1 AND conditional_2 AND ...).

    Args:
        target_function: The function whose probability you want to find.
        conditional_functions: A list of functions that must be present.
        commit_data: The dictionary of commit data.

    Returns:
        The calculated conditional probability as a float between 0.0 and 1.0.
    """
    # Use sets for efficient subset checking
    conditionals_set = set(conditional_functions)
    
    # Numerator: Counts commits where the target AND all conditionals are present
    joint_occurrence_count = 0
    
    # Denominator: Counts commits where ALL conditionals are present
    conditional_occurrence_count = 0

    for functions in commit_data.values():
        commit_set = set(functions)
        
        # Check if the condition (B, C, ...) is met
        if conditionals_set.issubset(commit_set):
            conditional_occurrence_count += 1
            
            # If the condition is met, check if the target (A) is also present
            if target_function in commit_set:
                joint_occurrence_count += 1

    # Avoid division by zero if the condition never occurs
    if conditional_occurrence_count == 0:
        return 0.0

    return joint_occurrence_count / conditional_occurrence_count

def find_commits_with_functions(prior_functions: list[str], commit_data: dict) -> list[str]:
    """
    Finds all commit hashes that contain every function from a given list.

    Args:
        prior_functions: A list of function names that must be present in a commit.
        commit_data: The dictionary of commit data (hash: [functions]).

    Returns:
        A list of commit hashes that match the criteria.
    """
    matching_commits = []
    # Use a set for the functions we're looking for, which allows for very fast checks.
    priors_set = set(prior_functions)

    # Iterate through each commit hash and its list of functions.
    for commit_hash, functions_in_commit in commit_data.items():
        # Convert the commit's function list to a set and check if our
        # set of priors is a subset of it. This is an efficient way to
        # confirm that all prior functions are present.
        if priors_set.issubset(set(functions_in_commit)):
            matching_commits.append(commit_hash)
            
    return matching_commits