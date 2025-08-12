# Contributing to Celestial Tracker

Thank you for your interest in contributing to Celestial Tracker! This document provides guidelines and instructions for contributing to the project.

## 🤝 Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct:
- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Accept feedback gracefully

## 🚀 Getting Started

1. **Fork the Repository**
   - Click the "Fork" button on GitHub
   - Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/celestial-tracker.git
   cd celestial-tracker
   ```

2. **Set Up Development Environment**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

3. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## 📝 How to Contribute

### Reporting Bugs

Before reporting a bug, please:
1. Check existing issues to avoid duplicates
2. Use the issue search to see if it's already reported
3. Collect relevant information:
   - Python version
   - Celestron Origin firmware version
   - Error messages and logs
   - Steps to reproduce

### Suggesting Features

We welcome feature suggestions! Please:
1. Check if the feature is already requested
2. Provide clear use cases
3. Explain why this feature would benefit users
4. Consider implementation complexity

### Submitting Pull Requests

1. **Before You Start**
   - Discuss major changes in an issue first
   - Ensure your code follows the project style
   - Update documentation as needed
   - Add tests for new functionality

2. **Pull Request Process**
   - Update README.md if needed
   - Ensure all tests pass
   - Update documentation
   - Request review from maintainers

3. **Commit Messages**
   Use clear, descriptive commit messages:
   ```
   feat: Add support for TLE auto-update
   fix: Correct coordinate transformation for southern hemisphere
   docs: Update installation instructions
   test: Add unit tests for trajectory calculation
   ```

## 🧪 Testing

Run tests before submitting:
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_sky_utils.py

# Run with coverage
pytest --cov=.
```

## 📏 Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Add docstrings to functions and classes
- Keep line length under 100 characters
- Use meaningful variable names

Example:
```python
async def calculate_pass_trajectory(
    satellite: EarthSatellite,
    observer: Topos,
    start_time: datetime,
    end_time: datetime
) -> List[Dict[str, float]]:
    """
    Calculate satellite trajectory points for a pass.
    
    Args:
        satellite: Skyfield satellite object
        observer: Observer location
        start_time: Pass start time (UTC)
        end_time: Pass end time (UTC)
        
    Returns:
        List of trajectory points with position data
    """
    # Implementation here
```

## 📚 Documentation

- Update relevant documentation in `docs/`
- Add docstrings to new functions
- Update README.md for user-facing changes
- Include examples for new features

## 🏷️ Issue Labels

- `bug` - Something isn't working
- `enhancement` - New feature or request
- `documentation` - Documentation improvements
- `good first issue` - Good for newcomers
- `help wanted` - Extra attention needed
- `question` - Further information requested

## 🔄 Development Workflow

1. **Stay Updated**
   ```bash
   git remote add upstream https://github.com/original/celestial-tracker.git
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make Changes**
   - Write clean, documented code
   - Add tests for new features
   - Update documentation

3. **Submit PR**
   - Push to your fork
   - Create pull request
   - Address review feedback

## 📋 Checklist for Pull Requests

- [ ] Code follows project style guidelines
- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] Commit messages are clear
- [ ] PR description explains changes
- [ ] No sensitive data included
- [ ] Tested with actual Celestron Origin (if applicable)

## 🎯 Priority Areas

We especially welcome contributions in these areas:
- Mount movement smoothing algorithms
- Additional satellite catalogs support
- Weather integration
- Machine learning for satellite detection
- Performance optimizations
- Documentation improvements
- Unit test coverage

## 💬 Getting Help

- Open an issue for bugs or features
- Join discussions for questions
- Check existing documentation
- Reach out to maintainers

## 🙏 Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- Project documentation

Thank you for contributing to Celestial Tracker! 🌟
