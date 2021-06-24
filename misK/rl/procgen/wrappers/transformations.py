import numpy as np
from gym import spaces

from misK.rl.procgen.wrappers.base import (VecEnvWrapper,
                                           VecEnvObservationWrapper)
from misK.rl.procgen.wrappers.proba import RunningMeanStd


class VecFrameStack(VecEnvWrapper):
    def __init__(self, venv, nstack):
        self.venv = venv
        self.nstack = nstack
        wos = venv.observation_space  # wrapped ob space
        low = np.repeat(wos.low, self.nstack, axis=-1)
        high = np.repeat(wos.high, self.nstack, axis=-1)
        self.stackedobs = np.zeros((venv.num_envs,) + low.shape, low.dtype)
        observation_space = spaces.Box(low=low, high=high, dtype=venv.observation_space.dtype)
        VecEnvWrapper.__init__(self, venv, observation_space=observation_space)

    def step_wait(self):
        obs, rews, news, infos = self.venv.step_wait()
        self.stackedobs = np.roll(self.stackedobs, shift=-1, axis=-1)
        for (i, new) in enumerate(news):
            if new:
                self.stackedobs[i] = 0
        self.stackedobs[..., -obs.shape[-1]:] = obs
        return self.stackedobs, rews, news, infos

    def reset(self):
        obs = self.venv.reset()
        self.stackedobs[...] = 0
        self.stackedobs[..., -obs.shape[-1]:] = obs
        return self.stackedobs


class VecExtractDictObs(VecEnvObservationWrapper):
    def __init__(self, venv, key, log=print):
        log(f"-> {self.__class__.__name__}", end=' ')
        self.key = key
        super().__init__(venv=venv,
                         observation_space=venv.observation_space.spaces[self.key])

    def process(self, obs):
        return obs[self.key]


class VecNormalize(VecEnvWrapper):
    """
    A vectorized wrapper that normalizes the observations
    and returns from an environment.
    """

    def __init__(self, venv, ob=True, ret=True, clipob=10., cliprew=10., gamma=0.99, epsilon=1e-8):
        VecEnvWrapper.__init__(self, venv)

        self.ob_rms = RunningMeanStd(shape=self.observation_space.shape) if ob else None
        self.ret_rms = RunningMeanStd(shape=()) if ret else None

        self.clipob = clipob
        self.cliprew = cliprew
        self.ret = np.zeros(self.num_envs)
        self.gamma = gamma
        self.epsilon = epsilon

    def step_wait(self):
        obs, rews, news, infos = self.venv.step_wait()
        for i in range(len(infos)):
            infos[i]['env_reward'] = rews[i]
        self.ret = self.ret * self.gamma + rews
        obs = self._obfilt(obs)
        if self.ret_rms:
            self.ret_rms.update(self.ret)
            rews = np.clip(rews / np.sqrt(self.ret_rms.var + self.epsilon), -self.cliprew, self.cliprew)
        self.ret[news] = 0.
        return obs, rews, news, infos

    def _obfilt(self, obs):
        if self.ob_rms:
            self.ob_rms.update(obs)
            obs = np.clip((obs - self.ob_rms.mean) / np.sqrt(self.ob_rms.var + self.epsilon), -self.clipob, self.clipob)
            return obs
        else:
            return obs

    def reset(self):
        self.ret = np.zeros(self.num_envs)
        obs = self.venv.reset()
        return self._obfilt(obs)


class TransposeFrame(VecEnvWrapper):
    def __init__(self, env, log=print):
        log(f"-> {self.__class__.__name__}", end=' ')
        super().__init__(venv=env)
        obs_shape = self.observation_space.shape
        self.observation_space = spaces.Box(low=0, high=255, shape=(obs_shape[2], obs_shape[0], obs_shape[1]),
                                            dtype=np.float32)

    def step_wait(self):
        obs, reward, done, info = self.venv.step_wait()
        return obs.transpose(0, 3, 1, 2), reward, done, info

    def reset(self):
        obs = self.venv.reset()
        return obs.transpose(0, 3, 1, 2)


class ScaledFloatFrame(VecEnvWrapper):
    def __init__(self, env, log=print):
        log(f"-> {self.__class__.__name__}", end=' ')
        super().__init__(venv=env)
        obs_shape = self.observation_space.shape
        self.observation_space = spaces.Box(low=0, high=1, shape=obs_shape, dtype=np.float32)

    def step_wait(self):
        obs, reward, done, info = self.venv.step_wait()
        return obs / 255.0, reward, done, info

    def reset(self):
        obs = self.venv.reset()
        return obs / 255.0
