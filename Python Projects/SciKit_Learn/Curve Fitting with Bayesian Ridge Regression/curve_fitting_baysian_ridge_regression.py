import numpy as np
from sklearn.linear_model import BayesianRidge
import matplotlib.pyplot as plt

def func(x):
    """Generate sine wave with frequency 2π"""
    return np.sin(2 * np.pi * x)


# Generate training data: 25 random points with Gaussian noise
size = 25
rng = np.random.RandomState(1234)
x_train = rng.uniform(0.0, 1.0, size)  # Random x values between 0 and 1
y_train = func(x_train) + rng.normal(scale=0.1, size=size)  # Add noise

# Generate test data: dense grid for smooth curve plotting
x_test = np.linspace(0.0, 1.0, 100)

# Transform to polynomial features (Vandermonde matrix) for cubic fitting
# increasing=True creates features [1, x, x², x³]
n_order = 3
X_train = np.vander(x_train, n_order + 1, increasing=True)
X_test = np.vander(x_test, n_order + 1, increasing=True)

# Initialize Bayesian Ridge model
# compute_score=True enables log marginal likelihood calculation
reg = BayesianRidge(tol=1e-6, fit_intercept=False, compute_score=True)

# Create side-by-side comparison plots
fig, axes = plt.subplots(1, 2, figsize=(8, 4))

for i, ax in enumerate(axes):
    # Configure different initial hyperparameters for comparison
    if i == 0:
        # Default initialization: tends to produce high bias (underfitting)
        init = [1 / np.var(y_train), 1.0]  # [alpha_init, lambda_init]
    elif i == 1:
        # Better initialization: smaller lambda reduces bias
        init = [1.0, 1e-3]
        reg.set_params(alpha_init=init[0], lambda_init=init[1])
    
    # Fit model and predict with uncertainty estimates
    reg.fit(X_train, y_train)
    ymean, ystd = reg.predict(X_test, return_std=True)

    # Plot ground truth sine wave
    ax.plot(x_test, func(x_test), color="blue", label="sin($2\\pi x$)")
    
    # Plot noisy training observations
    ax.scatter(x_train, y_train, s=50, alpha=0.5, label="observation")
    
    # Plot predicted mean curve
    ax.plot(x_test, ymean, color="red", label="predict mean")
    
    # Plot uncertainty band (mean ± 1 standard deviation)
    ax.fill_between(
        x_test, ymean - ystd, ymean + ystd, color="pink", alpha=0.5, label="predict std"
    )
    
    # Formatting
    ax.set_ylim(-1.3, 1.3)
    ax.legend()
    
    # Title showing initial parameters
    title = "$\\alpha$_init$={:.2f},\\ \\lambda$_init$={}$".format(init[0], init[1])
    if i == 0:
        title += " (Default)"
    ax.set_title(title, fontsize=12)
    
    # Text box showing final learned parameters and log marginal likelihood (L)
    # Higher L indicates better model fit
    text = "$\\alpha={:.1f}$\n$\\lambda={:.3f}$\n$L={:.1f}$".format(
        reg.alpha_, reg.lambda_, reg.scores_[-1]
    )
    ax.text(0.05, -1.0, text, fontsize=12)

plt.tight_layout()
plt.show()