"""Implements multi-source CCM.

Mansour, Y., Mohri, M., & Rostamizadeh, A. (2008). 
Domain adaptation with multiple sources. 
Advances in neural information processing systems, 21.
"""

# Author: Katherine Tsai <kt14@illinois.edu>
# MIT License


import numpy as np
from sklearn.neighbors import KernelDensity

from sklearn.preprocessing import normalize
from sklearn.neural_network import MLPClassifier, MLPRegressor


class MuiltiSourceCCM:
    """
    Implement multi source convex combinations.

    Mansour, Y., Mohri, M., & Rostamizadeh, A. (2008).
    Domain adaptation with multiple sources.
    Advances in neural information processing systems, 21.
    """

    def __init__(
        self,
        n_env,
        kde_kernel="gaussian",
        bandwidth=1.0,
        max_iter=300,
        task="c",
    ):
        self.n_env = n_env
        self.kde_kernel = kde_kernel
        self.bandwidth = bandwidth
        self.kde_x = []
        self.classifiers = []
        for _ in range(n_env):
            self.kde_x.append(
                KernelDensity(kernel=kde_kernel, bandwidth=bandwidth)
            )
            if task == "c":
                self.classifiers.append(
                    MLPClassifier(random_state=1, max_iter=max_iter)
                )
            else:
                self.classifiers.append(
                    MLPRegressor(random_state=1, max_iter=max_iter)
                )
        self.task = task

        # Assigned in fit()
        self.n_labels_ = None
        self.weight_ = None

    def fit(self, source_data, weight=None):
        # Fit KDE
        long_y = []

        for idx, train_data in enumerate(source_data):
            x_train = np.array(train_data["X"])
            y_train = np.array(train_data["Y"])
            if self.task == "c":
                long_y += list(np.unique(y_train))
                y_train = np.array(train_data["Y"])
            else:
                y_train = np.array(train_data["Y"]).ravel()

            self.classifiers[idx].fit(x_train, y_train)
            self.kde_x[idx].fit(x_train)
        if self.task == "c":
            self.n_labels_ = list(set(long_y))

        self.weight_ = weight

    def predict(self, x_new):
        weight_x = np.array(
            [np.exp(probx.score_samples(x_new)) for probx in self.kde_x]
        )
        normalized_weight_x = normalize(np.array(weight_x), axis=0)
        predict_y = np.array([clf.predict(x_new) for clf in self.classifiers])
        return np.sum((normalized_weight_x * predict_y).T, axis=1)

    def predict_proba(self, x_new):
        weight_x = np.array(
            [np.exp(probx.score_samples(x_new)) for probx in self.kde_x]
        )
        normalized_weight_x = normalize(np.array(weight_x), axis=0)
        predicty_proba = np.zeros(
            (x_new.shape[0], self.n_env, len(self.n_labels_))
        )

        for i, clf in enumerate(self.classifiers):
            predicty_proba[:, i, :] = clf.predict_proba(x_new)

        return np.sum(
            predicty_proba
            * normalized_weight_x[:, :, np.newaxis].transpose((1, 0, 2)),
            axis=1,
        )


class MultiSouceSimpleAdapt(MuiltiSourceCCM):
    """
    Implement multi source convex combinations.

    Mansour, Y., Mohri, M., & Rostamizadeh, A. (2008).
    Domain adaptation with multiple sources.
    Advances in neural information processing systems, 21.
    """

    def fit(self, source_data, weight=None):
        weight = np.ones(self.n_env) / self.n_env
        super().fit(source_data, weight=weight)


class MultiSourceUniform:
    """Ensemble prediction by uniformly weight the prediciton results."""

    def __init__(self, n_env, max_iter=300):
        self.n_env = n_env
        self.classifiers = [
            MLPClassifier(random_state=1, max_iter=max_iter)
            for _ in range(n_env)
        ]
        self.n_labels_ = None  # Assigned in fit()

    def fit(self, source_data):

        long_y = []
        for i, train_data in enumerate(source_data):

            x_train = train_data["X"]
            y_train = train_data["Y"]
            long_y += list(np.unique(y_train))

            self.classifiers[i].fit(x_train, y_train)
        self.n_labels_ = list(set(long_y))

        return self

    def predict(self, new_x):
        predict_y = np.zeros((new_x.shape[0], self.n_env))
        for i, clf in enumerate(self.classifiers):
            predict_y[:, i] = clf.predict(new_x)

        return np.sum(predict_y, axis=1) / self.n_env

    def predict_proba(self, new_x):

        predict_probay = np.zeros(
            (new_x.shape[0], self.n_env, len(self.n_labels_))
        )
        for i, clf in enumerate(self.classifiers):
            predict_probay[:, i, :] = clf.predict_proba(new_x)

        return np.sum(predict_probay, axis=1) / self.n_env


class MultiSourceUniformReg:
    """Ensemble prediction by uniformly weight the prediciton results."""

    def __init__(self, n_env, max_iter=300):
        self.n_env = n_env
        self.regressors = [
            MLPRegressor(random_state=1, max_iter=max_iter)
            for _ in range(n_env)
        ]

    def fit(self, source_data):

        for i, train_data in enumerate(source_data):

            x_train = train_data["X"]
            y_train = train_data["Y"].ravel()

            self.regressors[i].fit(x_train, y_train)

        return self

    def predict(self, new_x):
        predict_y = np.zeros((new_x.shape[0], self.n_env))
        for i, reg in enumerate(self.regressors):
            predict_y[:, i] = reg.predict(new_x)

        return np.sum(predict_y, axis=1) / self.n_env
