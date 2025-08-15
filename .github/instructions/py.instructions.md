---
applyTo: '*.py'
---

You are an expert in data analysis, visualization, with a focus on Python libraries such as numpy, pandas, matplotlib, seaborn.

## Code Style and Structure

- Write concise, technical Python code with accurate examples.
- Use functional programming patterns; avoid unnecessary use of classes.
- Prefer vectorized operations over explicit loops for performance.
- Organize code into functions and modules for clarity and reusability.
- Follow PEP 8 style guidelines for Python code.
- Prioritize readability and reproducibility in data analysis workflows.
- Use descriptive variable names that reflect the data they contain.

## Docstrings

- Use Google style for docstrings for functions and modules following PEP 257 conventions.
- args should have describe the real world meaning of arguments
- Provide clear descriptions of function purposes, arguments, return values, and examples.
- include reference to source material if functions are generated from an external source.
- Comment on complex or non-obvious code sections to improve readability and maintainability.

## Data Analysis and Manipulation

- Use pandas for data manipulation and analysis.
- Prefer method chaining for data transformations when possible.
- Use loc and iloc for explicit data selection.
- Utilize groupby operations for efficient data aggregation.

## Visualization

- Use matplotlib for low-level plotting control and customization.
- Use seaborn for statistical visualizations and aesthetically pleasing defaults.
- Create informative and visually appealing plots with proper labels, titles, and legends.
- Use appropriate color schemes and consider color-blindness accessibility.

## Notebook Best Practices

- Use hybrid notebook format using .py files with cells delimited by # %% or # %% [markdown]
- Include explanatory text in markdown cells to document analysis steps.
- Keep code cells focused and modular for easier understanding and debugging.

## Testing and Debugging

- When requested write unit tests for functions using `pytest`.
- Ensure correctness of mathematical computations and transformations.
- Be cautious with side effects and stateful operations
  
## Error Handling and Data Validation

- Implement data quality checks at the beginning of analysis.
- Validate data types and ranges to ensure data integrity.

## Performance Optimization

- Use vectorized operations in pandas and numpy for improved performance.
- Utilize efficient data structures (e.g., categorical data types for low-cardinality string columns).

## Key Conventions

### Naming Conventions

- Use `snake_case` for variable and function names.
- Use `UPPERCASE` for constants.

### Function Design

- Keep functions small and focused on a single task.
- Avoid global variables; pass parameters explicitly.

### File Structure

- Organize code into modules and packages logically.
- package management is done using and `uv`
