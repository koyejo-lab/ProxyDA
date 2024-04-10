# coding=utf-8
# Copyright 2023 The Google Research Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Define simulators for synthetic data for a causal generative process with
latent confounders, mediating concepts, and proxies.
"""


import jax
import numpy as np
import scipy
from sklearn.preprocessing import OneHotEncoder


class Simulator:
    """Generates simulated data following a causal generative process.

    To use this class, either create a subclass with get_default_param_dict
    defined (see UnivariateSimulator or MultivariateSimulator for examples)
    or provide a complete param_dict to the __init__ method of this class.
    """

    def __init__(
        self,
        param_dict=None,
    ):
        """Initializes simulation.

        Arguments:
          param_dict: provided param_dict will override default parameters.
        """

        self.param_dict = self.get_default_param_dict()

        if param_dict is not None:
            for key, value in param_dict.items():
                self.param_dict[key] = value
        self.initialize()

    def get_default_param_dict(self):
        """Defines default simulation parameters."""
        return {}

    def initialize(self):
        """Helper function for initializing simulation parameters.

        Modifies self.param_dict, setting self.param_dict[{key}] = {key}_coeff *
        {key}_mat. This allows for straightforward modification of the scaling
        associated with the transformations in the generative process.
        """
        for key in [
            "mu_w_u",
            "mu_x_u",
            "mu_y_c",
            "mu_y_u",
            "mu_c_u",
            "mu_c_x",
        ]:
            self.param_dict[key] = (
                self.param_dict[f"{key}_coeff"] * self.param_dict[f"{key}_mat"]
            )

    def get_samples(self, p_u=None, seed=42):
        """Generates samples from the simulation.

        Arguments:
          p_u: array that specifies the mixture proportions over latent categories u
          seed: a random seed

        Returns:
          a dict containing generated data
        """

        rng = jax.random.PRNGKey(seed)
        _, k0, k1, k2 = jax.random.split(rng, 4)

        ## Generate u
        if p_u is None:
            p_u = self.param_dict["p_u"]

        u = jax.random.bernoulli(
            k0, p_u[1], shape=(self.param_dict["num_samples"],)
        ).astype(int)
        u_one_hot = OneHotEncoder(sparse_output=False).fit_transform(
            u.reshape(-1, 1)
        )

        ## Generate w
        w = jax.random.multivariate_normal(
            key=k1,
            mean=u_one_hot @ self.param_dict["mu_w_u"],
            cov=np.eye(self.param_dict["k_w"]),
        )
        w = np.array(w).astype(np.float64)

        ## Generate x
        x = jax.random.multivariate_normal(
            key=k2,
            mean=u_one_hot @ self.param_dict["mu_x_u"],
            cov=np.eye(self.param_dict["k_x"]),
        )
        x = np.array(x).astype(np.float64)

        ## Generate c (binary or multilabel, depending on dimensionality of c)
        c_logits = (
            x.dot(self.param_dict["mu_c_x"])[
                np.arange(self.param_dict["num_samples"]), np.squeeze(u), :
            ]
            + (u_one_hot @ self.param_dict["mu_c_u"]).reshape(
                -1, self.param_dict["k_c"]
            )
            + np.random.normal(
                scale=self.param_dict["sd_c"],
                size=(self.param_dict["num_samples"], self.param_dict["k_c"]),
            ).reshape(-1, self.param_dict["k_c"])
        )
        c = np.random.binomial(n=1, p=scipy.special.expit((c_logits))).reshape(
            -1, self.param_dict["k_c"]
        )

        ## Generate y
        y_logits = (
            c.dot(self.param_dict["mu_y_c"].T)[
                np.arange(self.param_dict["num_samples"]), np.squeeze(u)
            ].reshape(-1, 1)
            + (u_one_hot @ self.param_dict["mu_y_u"]).reshape(-1, 1)
            + np.random.normal(
                scale=self.param_dict["sd_y"],
                size=self.param_dict["num_samples"],
            ).reshape(-1, 1)
        )
        y = np.squeeze(
            np.random.binomial(n=1, p=scipy.special.expit((y_logits)))
        )
        y_one_hot = OneHotEncoder(sparse_output=False).fit_transform(
            y.reshape(-1, 1)
        )

        return {
            "u": u,
            "x": x,
            "w": w,
            "c": c,
            "c_logits": c_logits,
            "y": y,
            "y_logits": y_logits,
            "y_one_hot": y_one_hot,
        }

    def update_param_dict(self, **kwargs):
        if kwargs is not None:
            for key, value in kwargs.items():
                self.param_dict[key] = value


class UnivariateSimulator(Simulator):
    """Defines a simulation where all variables are univariate."""

    def get_default_param_dict(self):
        return {
            "num_samples": 10000,
            "k_w": 1,
            "k_x": 1,
            "k_c": 1,
            "k_y": 1,
            "mu_w_u_coeff": 1,
            "mu_x_u_coeff": 1,
            "mu_y_u_coeff": 1,
            "mu_y_c_coeff": 4,
            "mu_c_u_coeff": 1,
            "mu_c_x_coeff": 4,
            "mu_w_u_mat": np.array([[-1, 1]]).T,  # k_u x k_w
            "mu_x_u_mat": np.array([[-1, 1]]).T,  # k_u x k_x
            "mu_c_u_mat": np.array([[1, -1]]).T,  # k_u x k_c
            "mu_c_x_mat": np.array([[[-1, 1]]]).T,  # k_u x k_x x k_c
            "mu_y_c_mat": np.array(
                [[-1, -2]]
            ).T,  # k_u x k_c (x k_y=1 implicitly)
            "mu_y_u_mat": np.array([[1, 2]]).T,  # k_u x 1
            "sd_c": 0.5,
            "sd_y": 0.1,
            "p_u": [0.5, 0.5],
        }


class MultivariateSimulator(Simulator):
    """Defines a simulation where variables are multivariate."""

    def get_default_param_dict(self):
        param_dict = {
            "num_samples": 10000,
            "k_w": 3,
            "k_x": 2,
            "k_c": 3,
            "k_y": 1,
            "mu_w_u_coeff": 1,
            "mu_x_u_coeff": 1,
            "mu_y_u_coeff": 2,
            "mu_y_c_coeff": 2,
            "mu_c_u_coeff": 1,
            "mu_c_x_coeff": 3,
            "mu_w_u_mat": np.array([[-1, 1, 2], [1, -1, -1]]),  # k_u x k_w
            "mu_x_u_mat": np.array([[-1, 1], [1, -1]]),  # k_u x k_x
            "mu_c_u_mat": np.array([[-1, 2, -4], [-1, 1, 2]]),  # k_u x k_c
            "mu_c_x_mat": np.array(
                [[[-2, 1, -1], [3, -2, 2]], [[1, -2, -3], [-1, 2, 3]]]
            ),  # k_u x k_x x k_c
            "mu_y_c_mat": np.array([[2, -2, -1], [1, -1, -2]]),  # k_u x k_c
            "mu_y_u_mat": np.array([[1, 2]]).T,  # k_u x 1
            "sd_c": 0.5,
            "sd_y": 0.1,
            "p_u": [0.5, 0.5],
        }
        return param_dict


class MixedSimulator(Simulator):
    """Multivariate X and C. Univariate W. Binary Y."""

    def get_default_param_dict(self):
        param_dict = {
            "num_samples": 10000,
            "k_w": 1,
            "k_x": 2,
            "k_c": 3,
            "k_y": 1,
            "mu_w_u_coeff": 1,
            "mu_x_u_coeff": 1,
            "mu_y_u_coeff": 2,
            "mu_y_c_coeff": 2,
            "mu_c_u_coeff": 1,
            "mu_c_x_coeff": 3,
            "mu_w_u_mat": np.array([[-1, 1]]).T,
            "mu_x_u_mat": np.array([[-1, 1], [1, -1]]),  # k_u x k_x
            "mu_c_u_mat": np.array([[-2, 2, 2], [-1, 1, 2]]),  # k_u x k_c
            "mu_c_x_mat": np.array(
                [[[-2, 2, -1], [1, -2, -3]], [[2, -2, 1], [-1, 2, 3]]]
            ),  # k_u x k_x x k_c
            "mu_y_c_mat": np.array([[3, -2, -1], [3, -1, -2]]),  # k_u x k_c
            "mu_y_u_mat": np.array([[1, 1]]).T,  # k_u x 1
            "sd_c": 0.0,
            "sd_y": 0.0,
            "p_u": [0.5, 0.5],
        }
        return param_dict


class MultiWSimulator(Simulator):
    """Generates data with multiple settings for the proxy variable W, holding other variables fixed."""

    def initialize(self):
        """Helper function for initializing simulation parameters.

        Multiples {prefix}_coeff * {prefix}_mat, modifying self.param_dict
        """
        for key in ["mu_x_u", "mu_y_c", "mu_y_u", "mu_c_u", "mu_c_x"]:
            self.param_dict[key] = (
                self.param_dict[f"{key}_coeff"] * self.param_dict[f"{key}_mat"]
            )

        for mu_w_u_coeff in self.param_dict["mu_w_u_coeff_list"]:
            self.param_dict[f"mu_w_u_{mu_w_u_coeff}"] = (
                mu_w_u_coeff * self.param_dict["mu_w_u_mat"]
            )

    def get_samples(self, p_u=None, seed=42):
        """Generates samples from the simulation.

        Arguments:
          p_u: array that specifies the mixture proportions over latent categories u
          seed: a random seed

        Returns:
          a dict containing generated data
        """
        result = {}
        rng = jax.random.PRNGKey(seed)
        _, k0, k1 = jax.random.split(rng, 3)

        ## Generate u
        if p_u is None:
            p_u = self.param_dict["p_u"]

        u = np.random.binomial(1, p_u[1], size=self.param_dict["num_samples"])
        u_one_hot = OneHotEncoder(sparse_output=False).fit_transform(
            u.reshape(-1, 1)
        )

        ## Generate w
        for mu_w_u_coeff in self.param_dict["mu_w_u_coeff_list"]:
            w = jax.random.multivariate_normal(
                key=k0,
                mean=u_one_hot @ self.param_dict[f"mu_w_u_{mu_w_u_coeff}"],
                cov=np.eye(self.param_dict["k_w"]),
            )
            result[f"w_{mu_w_u_coeff}"] = np.array(w).astype(np.float64)

        ## Generate x
        x = jax.random.multivariate_normal(
            key=k1,
            mean=u_one_hot @ self.param_dict["mu_x_u"],
            cov=np.eye(self.param_dict["k_x"]),
        )
        x = np.array(x).astype(np.float64)

        ## Generate c (binary or multilabel, depending on dimensionality of c)
        c_logits = (
            x.dot(self.param_dict["mu_c_x"])[
                np.arange(self.param_dict["num_samples"]), np.squeeze(u), :
            ]
            + (u_one_hot @ self.param_dict["mu_c_u"]).reshape(
                -1, self.param_dict["k_c"]
            )
            + np.random.normal(
                scale=self.param_dict["sd_c"],
                size=(self.param_dict["num_samples"], self.param_dict["k_c"]),
            ).reshape(-1, self.param_dict["k_c"])
        )
        c = np.random.binomial(n=1, p=scipy.special.expit((c_logits))).reshape(
            -1, self.param_dict["k_c"]
        )

        ## Generate y
        y_logits = (
            c.dot(self.param_dict["mu_y_c"].T)[
                np.arange(self.param_dict["num_samples"]), np.squeeze(u)
            ].reshape(-1, 1)
            + (u_one_hot @ self.param_dict["mu_y_u"]).reshape(-1, 1)
            + np.random.normal(
                scale=self.param_dict["sd_y"],
                size=self.param_dict["num_samples"],
            ).reshape(-1, 1)
        )
        y = np.squeeze(
            np.random.binomial(n=1, p=scipy.special.expit((y_logits)))
        )
        y_one_hot = OneHotEncoder(sparse_output=False).fit_transform(
            y.reshape(-1, 1)
        )

        return result | {
            "u": u,
            "x": x,
            "c": c,
            "c_logits": c_logits,
            "y": y,
            "y_logits": y_logits,
            "y_one_hot": y_one_hot,
        }

    def get_default_param_dict(self):
        param_dict = {
            "num_samples": 10000,
            "k_w": 1,
            "k_x": 2,
            "k_c": 3,
            "k_y": 1,
            "mu_w_u_coeff_list": [1, 2, 3],
            "mu_x_u_coeff": 1,
            "mu_y_u_coeff": 2,
            "mu_y_c_coeff": 2,
            "mu_c_u_coeff": 1,
            "mu_c_x_coeff": 3,
            "mu_w_u_mat": np.array([[-1, 1]]).T,
            "mu_x_u_mat": np.array([[-1, 1], [1, -1]]),  # k_u x k_x
            "mu_c_u_mat": np.array([[-2, 2, 2], [-1, 1, 2]]),  # k_u x k_c
            "mu_c_x_mat": np.array(
                [[[-2, 2, -1], [1, -2, -3]], [[2, -2, 1], [-1, 2, 3]]]
            ),  # k_u x k_x x k_c
            "mu_y_c_mat": np.array([[3, -2, -1], [3, -1, -2]]),  # k_u x k_c
            "mu_y_u_mat": np.array([[1, 1]]).T,  # k_u x 1
            "sd_c": 0.0,
            "sd_y": 0.0,
            "p_u": [0.5, 0.5],
        }
        return param_dict


class MultiEnvMultiWSimulator(Simulator):
    """Generates data with multiple settings for the proxy variable W, holding other variables fixed."""

    def initialize(self):
        """Helper function for initializing simulation parameters.

        Multiples {prefix}_coeff * {prefix}_mat, modifying self.param_dict
        """
        for key in ["mu_x_u", "mu_y_c", "mu_y_u", "mu_c_u", "mu_c_x"]:
            self.param_dict[key] = (
                self.param_dict[f"{key}_coeff"] * self.param_dict[f"{key}_mat"]
            )

        for mu_w_u_coeff in self.param_dict["mu_w_u_coeff_list"]:
            self.param_dict[f"mu_w_u_{mu_w_u_coeff}"] = (
                mu_w_u_coeff * self.param_dict["mu_w_u_mat"]
            )

    def get_samples(self, p_u=None, seed=42):
        """Generates samples from the simulation.

        Arguments:
          p_u: array that specifies the mixture proportions over latent categories u
          seed: a random seed

        Returns:
          a dict containing generated data
        """
        result = {}
        rng = jax.random.PRNGKey(seed)
        _, k0, k1 = jax.random.split(rng, 3)

        ## Generate u
        if p_u is None:
            p_u = self.param_dict["p_u"]

        u = np.random.binomial(1, p_u[1], size=self.param_dict["num_samples"])
        u_one_hot = OneHotEncoder(sparse_output=False).fit_transform(
            u.reshape(-1, 1)
        )

        ## Generate w
        for mu_w_u_coeff in self.param_dict["mu_w_u_coeff_list"]:
            w = jax.random.multivariate_normal(
                key=k0,
                mean=u_one_hot @ self.param_dict[f"mu_w_u_{mu_w_u_coeff}"],
                cov=np.eye(self.param_dict["k_w"]),
            )
            result[f"w_{mu_w_u_coeff}"] = np.array(w).astype(np.float64)

        ## Generate x
        x = jax.random.multivariate_normal(
            key=k1,
            mean=u_one_hot @ self.param_dict["mu_x_u"],
            cov=np.eye(self.param_dict["k_x"]),
        )
        x = np.array(x).astype(np.float64)

        ## Generate c (binary or multilabel, depending on dimensionality of c)
        c_logits = (
            x.dot(self.param_dict["mu_c_x"])[
                np.arange(self.param_dict["num_samples"]), np.squeeze(u), :
            ]
            + (u_one_hot @ self.param_dict["mu_c_u"]).reshape(
                -1, self.param_dict["k_c"]
            )
            + np.random.normal(
                scale=self.param_dict["sd_c"],
                size=(self.param_dict["num_samples"], self.param_dict["k_c"]),
            ).reshape(-1, self.param_dict["k_c"])
        )
        c = np.random.binomial(n=1, p=scipy.special.expit((c_logits))).reshape(
            -1, self.param_dict["k_c"]
        )

        ## Generate y
        y_logits = (
            c.dot(self.param_dict["mu_y_c"].T)[
                np.arange(self.param_dict["num_samples"]), np.squeeze(u)
            ].reshape(-1, 1)
            + (u_one_hot @ self.param_dict["mu_y_u"]).reshape(-1, 1)
            + np.random.normal(
                scale=self.param_dict["sd_y"],
                size=self.param_dict["num_samples"],
            ).reshape(-1, 1)
        )
        y = np.squeeze(
            np.random.binomial(n=1, p=scipy.special.expit((y_logits)))
        )
        y_one_hot = OneHotEncoder(sparse_output=False).fit_transform(
            y.reshape(-1, 1)
        )

        return result | {
            "u": u,
            "x": x,
            "c": c,
            "c_logits": c_logits,
            "y": y,
            "y_logits": y_logits,
            "y_one_hot": y_one_hot,
        }

    def get_default_param_dict(self):
        param_dict = {
            "num_samples": 10000,
            "k_w": 1,
            "k_x": 2,
            "k_c": 3,
            "k_y": 1,
            "mu_w_u_coeff_list": [1, 2, 3],
            "mu_x_u_coeff": 1,
            "mu_y_u_coeff": 2,
            "mu_y_c_coeff": 2,
            "mu_c_u_coeff": 1,
            "mu_c_x_coeff": 3,
            "mu_w_u_mat": np.array([[-1, 1]]).T,
            "mu_x_u_mat": np.array([[-1, 1], [1, -1]]),  # k_u x k_x
            "mu_c_u_mat": np.array([[-2, 2, 2], [-1, 1, 2]]),  # k_u x k_c
            "mu_c_x_mat": np.array(
                [[[-2, 2, -1], [1, -2, -3]], [[2, -2, 1], [-1, 2, 3]]]
            ),  # k_u x k_x x k_c
            "mu_y_c_mat": np.array([[3, -2, -1], [3, -1, -2]]),  # k_u x k_c
            "mu_y_u_mat": np.array([[1, 1]]).T,  # k_u x 1
            "sd_c": 0.0,
            "sd_y": 0.0,
            "p_u": [0.5, 0.5],
        }
        return param_dict


def process_data(data_dict, w_cols=["w_1", "w_2", "w_3"]):
    result = data_dict.copy()
    for w_col in w_cols:
        result[f"{w_col}_binary"] = 1.0 * (result[f"{w_col}"] > 0)
        result[f"{w_col}_one_hot"] = OneHotEncoder(
            sparse_output=False
        ).fit_transform(result[f"{w_col}_binary"])
    result["u_one_hot"] = OneHotEncoder(sparse_output=False).fit_transform(
        result["u"].reshape(-1, 1)
    )
    return result


def generate_data(p_u, seed, num_samples, partition_dict, param_dict=None):

    sim = MultiWSimulator(param_dict=param_dict)
    samples_dict = {}
    for i, (partition_key, partition_frac) in enumerate(
        partition_dict.items()
    ):
        num_samples_partition = int(partition_frac * num_samples)
        sim.update_param_dict(num_samples=num_samples_partition, p_u=p_u)
        samples_dict[partition_key] = process_data(
            sim.get_samples(seed=seed + 15 * i)
        )
    return samples_dict


def tidy_w(data_dict, w_value):
    result = data_dict.copy()
    for key in result.keys():
        result[key]["w"] = result[key][f"w_{w_value}"]
        result[key]["w_binary"] = result[key][f"w_{w_value}_binary"]
        result[key]["w_one_hot"] = result[key][f"w_{w_value}_one_hot"]
    return result


def from_Z_to_U(z_indicator, task=None):
    if task == 1:
        pu_lookup = {0: 0.1, 1: 0.2, 2: 0.3, 3: 0.4, 4: 0.9}
    elif task == 2:
        pu_lookup = {0: 0.4, 1: 0.5, 2: 0.6, 3: 0.4, 4: 0.9}
    elif task == 3:
        pu_lookup = {0: 0.7, 1: 0.8, 2: 0.9, 3: 0.4, 4: 0.4}
    else:
        raise NotImplementedError("Task not implemented.")

    return pu_lookup[z_indicator], len(pu_lookup)


def generate_multienv_data(
    z_indicator, seed, num_samples, task, partition_dict, param_dict=None
):

    pu_0, z_size = from_Z_to_U(z_indicator, task=task)
    p_u = [pu_0, 1 - pu_0]
    sample_dict = generate_data(
        p_u, seed, num_samples, partition_dict, param_dict=param_dict
    )
    for p in partition_dict.keys():
        sample_dict[p]["n_env"] = z_size

    return sample_dict


def from_U_to_Z(U, seed, num_samples):
    np.random.seed(seed)

    Z = np.array(np.random.normal(scale=1, size=num_samples))

    return Z + U


def generate_multienv_data_continuous(
    p_u, seed, num_samples, partition_dict, param_dict=None
):

    sample_dict = generate_data(
        p_u, seed, num_samples, partition_dict, param_dict=param_dict
    )
    slice_keys = sample_dict.keys()
    for key in slice_keys:
        print("working on dir")
        n_s = sample_dict[key]["u"].shape[0]
        sample_dict[key]["Z"] = from_U_to_Z(sample_dict[key]["u"], seed, n_s)

    return sample_dict
