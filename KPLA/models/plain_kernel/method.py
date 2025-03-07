"""
Implementation of the base kernel estimator
"""

# Author: Katherine Tsai <kt14@illinois.edu>
# License: MIT

import copy

import jax.numpy as jnp
import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.metrics import accuracy_score
from sklearn.metrics import log_loss
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import normalize
from sklearn.base import BaseEstimator


# Define Sklearn evaluation functions
def soft_accuracy(y_true, y_pred, threshold=0.5, **kwargs):
    return accuracy_score(y_true, y_pred >= threshold, **kwargs)


def log_loss64(y_true, y_pred, **kwargs):
    return log_loss(y_true, y_pred.astype(np.float64), **kwargs)


evals_sklearn = {
    "hard_acc": accuracy_score,
    "auc": roc_auc_score,
}


def split_data_widx(data, split_index):
    """Split data with indices, return dictionary.

    Args:
        data: dict
        split_idx: ndarray
    Returns:
        sub_data: dict
    """
    sub_data = {}
    keys = data.keys()
    for key in keys:
        if len(data[key].shape) > 1:
            sub_data[key] = jnp.array(data[key][split_index, :])
        else:
            sub_data[key] = jnp.array(data[key][split_index])
    return sub_data


class KernelMethod(BaseEstimator):
    """
    Base estimator for the adaptation
    split_data(), predict(), evaluation(), are implemented by the child class
    """

    def __init__(
        self,
        source_train,
        target_train,
        source_test,
        target_test,
        split=False,
        scale=1,
        lam_set=None,
        method_set=None,
        kernel_dict=None,
        thre=0.5,
    ):
        """Initialize parameters.

        Args:
            source_train: dict, keys: C,W,X,Y
            target_train: dict, keys: C, W, X, Y
            source_test:  dict, keys: X, Y
            target_test:  dict, keys: X, Y
            split: Boolean, split the training dataset or not.
                If True, the samples are evenly split into groups.
                Hence, each estimator receive smaller number of training samples.
            scale: length-scale of the kernel function, default: 1.
            lam_set: a dict of tuning parameter,
                set None for leave-one-out estimation
            For example, lam_set={"cme": lam1, "h0": lam2, "m0": lam3}
            method_set: a dictionary of optimization methods for
                different estimators, default is "original"
            kernel_dict: a dictionary of specified kernel functions
        """
        self.source_train = source_train
        self.target_train = target_train
        self.source_test = source_test
        self.target_test = target_test
        self.sc = scale
        self.split = split
        self._is_fitted = False
        self.calib_domain = "source"
        self.thre = thre
        if lam_set is None:
            lam_set = {"cme": None, "h0": None, "m0": None}

        self.lam_set = lam_set

        if method_set is None:
            method_set = {
                "cme": "original",
                "h0": "original",
                "m0": "original",
            }
        self.method_set = method_set

        if kernel_dict is None:
            kernel_dict["cme_w_xc"] = {
                "X": "rbf",
                "C": "rbf",
                "Y": "rbf",
            }  # Y is W
            kernel_dict["cme_wc_x"] = {
                "X": "rbf",
                "Y": [
                    {"kernel": "rbf", "dim": 2},
                    {"kernel": "rbf", "dim": 1},
                ],
            }  # Y is (W,C)
            kernel_dict["cme_c_x"] = {"X": "rbf", "Y": "rbf"}  # Y is C
            kernel_dict["cme_w_x"] = {"X": "rbf", "Y": "rbf"}  # Y is W
            kernel_dict["h0"] = {"C": "rbf"}
            kernel_dict["m0"] = {"C": "rbf", "X": "rbf"}

        self.kernel_dict = kernel_dict
        self.source_estimator = None
        self.target_estimator = None

    def get_params(self):
        params = {}
        params["lam_set"] = self.lam_set
        params["method_set"] = self.method_set
        params["kernel_dict"] = self.kernel_dict
        params["split"] = self.split
        params["scale"] = self.sc

        return params

    def set_params(self, params):
        self.lam_set = params["lam_set"]
        self.method_set = params["method_set"]
        self.kernel_dict = params["kernel_dict"]
        self.split = params["split"]
        self.sc = params["scale"]

    def fit(self, task="r", train_target=True):
        """fit the model
        Args:
          task: "r" for regression,
                "c" for classification (multi-head regression)
          train_target: train target domain or not, Boolean
                        if False, only learn the adaptation part
        """
        # Split dataset
        if self.split:
            self.split_data()
        # Learn estimators from the source domain
        self.source_estimator = self._fit_one_domain(self.source_train, task)

        # Learn estimators from the target domain
        if train_target:
            self.target_estimator = self._fit_one_domain(
                self.target_train, task
            )
        else:
            self.target_estimator = self._fit_target_domain(
                self.target_train, task
            )

        self._is_fitted = True
        if task == "c":
            self.classes_ = [i for i in range(self.source_train["Y"].shape[1])]

    def _fit_one_domain(self, domain_data, task):
        """Fits the model to the training data."""
        raise NotImplementedError("Implemented in child class.")

    def _fit_target_domain(self, domain_data, task):
        """Fits the model to the training data."""
        raise NotImplementedError("Implemented in child class.")

    def split_data(self):
        """Splits training data."""
        raise NotImplementedError("Implemented in child class.")

    def predict(self):
        """Prediction."""
        raise NotImplementedError("Implemented in child class.")

    def evaluation(self):
        """Evaluate the model."""
        raise NotImplementedError("Implemented in child class.")

    def score(
        self, predict_y, test_y, task="r", predicty_prob=None, thres=0.5
    ):
        """Score function.

        Args:
          predict_y:     prediected Y, (n_sample, ) or (n_sample, n_classes)
          test_y:        true Y, (n_sample, ) or (n_samples, n_classes)
          task:          evaluation task:
                         "r" for regression,
                         "c" for classification
          predicty_prob: the probability of each class (n_sample, n_classes)
          thres:         threshold for classification, float
        """
        err_message = (
            "Unresolveable shape mismatch between test_y and predict_y"
        )
        test_y = test_y.squeeze()
        predict_y = predict_y.squeeze()
        if task == "r":  # MSE score for regression task
            if test_y.shape > predict_y.shape:
                if not test_y.ndim == predict_y.ndim + 1:
                    if not test_y.shape[:-1] == predict_y.shape:
                        raise AssertionError(err_message)

                predict_y = predict_y.reshape(test_y.shape)
            elif test_y.shape < predict_y.shape:
                if not test_y.ndim + 1 == predict_y.ndim:
                    if not test_y.shape == predict_y.shape[:-1]:
                        raise AssertionError(err_message)
                test_y = test_y.reshape(predict_y.shape)
            error = {
                "l2": mean_squared_error(np.array(test_y), np.array(predict_y))
            }

        elif task == "c":  # Classification task
            error = {}

            if len(predict_y.shape) >= 2:
                if predict_y.shape[1] >= 2:
                    # For multi-head regression, i.e., Y is one-hot incoded
                    testy_label = np.array(jnp.argmax(jnp.abs(test_y), axis=1))
                    predicty_label = np.array(
                        jnp.argmax(jnp.abs(predict_y), axis=1)
                    )
                    if predicty_prob is None:
                        predicty_prob = normalize(
                            np.array(jnp.abs(predict_y)), axis=1
                        )
                else:
                    # For binary classfication where Y is {-1, 1}
                    testy_label = copy.copy(test_y)
                    idx = np.where(testy_label == -1)[0]
                    testy_label[idx] = 0
                    idx1 = np.where(predict_y[:, -1] >= thres)[0]
                    predicty_label = np.zeros(
                        predict_y.shape[0], dtype=np.int8
                    )
                    predicty_label[idx1] = 1
                    if predicty_prob is None:
                        predicty_prob = predict_y

            else:
                # For binary classfication where Y is {-1, 1}
                idx1 = np.where(predict_y >= thres)[0]

                testy_label = copy.copy(test_y)

                # correct -1 to 0
                idx = np.where(testy_label == -1)[0]
                testy_label[idx] = 0
                predicty_label = np.zeros(predict_y.shape[0], dtype=np.int8)
                predicty_label[idx1] = 1
                if predicty_prob is None:
                    predicty_prob = predict_y[:, np.newaxis]

            for eva in evals_sklearn.items():
                if eva[0] == "hard_acc":
                    error[eva[0]] = eva[1](testy_label, predicty_label)
                else:
                    error[eva[0]] = eva[1](testy_label, predicty_prob[:, -1])
        return error

    def __sklearn_is_fitted__(self):
        """Check fitted status and return a Boolean value."""
        return hasattr(self, "_is_fitted") and self._is_fitted
