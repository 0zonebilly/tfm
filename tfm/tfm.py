#!/usr/bin/env python
"""
Compute Temporal Functional Modes
"""

import argparse
import ast
import logging
import os
import warnings

import nibabel as nib
import numpy as np
from sklearn.decomposition import FastICA

warnings.filterwarnings("error")


class MelodicData:

    def __init__(self, directory, labelfile='hand_classification.txt'):

        self.directory = directory
        self.mix = self.get_melodic_mix(directory)
        self.n_components = self.mix.shape[1]
        self.labels = self.get_labels(directory, labelfile)
        self.signal = self.mix[:, self.labels]
        self.shape = self._get_rsns().shape[:-1]
        self.affine = self._get_rsns().affine

    def get_melodic_mix(self, directory):
        """Read in the spatial melodic mix.
        """
        mixfile = os.path.join(directory, 'melodic_mix')
        mix = np.loadtxt(mixfile)
        return mix

    def get_labels(self, directory, labelfile):
        """Parse the classification file.
        """
        labelfile = os.path.join(directory, labelfile)
        with open(labelfile, 'r') as f:
            last_line = [line for line in f][-1]
        noise = [x - 1 for x in ast.literal_eval(last_line)]
        return [x for x in range(self.n_components)
                if x not in noise]

    def _get_rsns(self):
        """Load melodic IC from directory.
        """
        return nib.load(os.path.join(self.directory,
                                     'melodic_IC.nii.gz'))

    @property
    def rsns(self):
        """
        Only returns signal components from melodic IC.
        """
        rsns = self._get_rsns()
        temporal = rsns.shape[-1]
        data = np.reshape(rsns.get_data(), (-1, temporal))[:, self.labels]
        return data


class TFM:

    def __init__(self, n_components=30, max_iter=20_000, tol=0.0001,
                 algorithm='deflation', random_state=None):

        self.ica = FastICA(max_iter=max_iter, tol=tol,
                           n_components=n_components,
                           algorithm=algorithm,
                           random_state=random_state)

    def fit_transform_melodic(self, melodic_data):
        """Take a MelodicData object and unmix it.
        """
        sources = self.ica.fit_transform(melodic_data.signal)
        rsns = melodic_data.rsns
        tfm = np.dot(rsns, self.ica.mixing_)
        return nib.Nifti1Image(np.reshape(tfm,
                                          (*melodic_data.shape, -1)),
                               melodic_data.affine), sources


def main(args):

    logging.basicConfig(format="%(asctime)s [%(levelname)s]: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                        level=logging.INFO)

    if os.path.isabs(args.outputdir):
        outdir = args.outputdir
    else:
        outdir = os.path.join(args.inputdir, 'tfm.ica')

    def out(name):
        return os.path.join(outdir, name)

    if not args.dryrun:
        assert not os.path.exists(outdir)
        os.makedirs(outdir)
        assert os.path.exists(args.inputdir)
    else:
        print(out('melodic_IC.nii.gz'))
        print(out('melodic_mix'))
        return

    # Load data
    logging.info("Loading Melodic Data")
    melodic_data = MelodicData(args.inputdir, args.labelfile)

    # Parse user inputs
    n_components = args.n_components or melodic_data.n_components
    tolerance = args.tolerance
    max_iter = args.max_iter

    # Compute TFMs.
    logging.info("Computing TFMs")
    try_counter = 1
    while True:
        try:
            tfm_ica = TFM(n_components=n_components,
                          max_iter=max_iter,
                          tol=tolerance,
                          random_state=np.random.randint(0, 2**32 - 1))
            tfms, sources = tfm_ica.fit_transform_melodic(melodic_data)
        except UserWarning:
            try_counter += 1
            print('ICA did not converge. Retrying with new seed.')
            if try_counter > 15:
                raise
            else:
                pass
        else:
            logging.info(f"ICA successful after {try_counter} attempts.")
            break


    # Save outputs
    logging.info(f"Saving outputs to directory {outdir}")
    tfms.to_filename(out('melodic_IC.nii.gz'))
    np.savetxt(out('melodic_mix'), sources, delimiter='  ', fmt='%.6f')
    np.savetxt(out('melodic_FTmix'), np.abs(np.fft.rfft(sources)),
               delimiter='  ', fmt='%.6f')


def run_tfm():

    parser = _cli_parser()
    args = parser.parse_args()
    main(args)


def _cli_parser():
    parser = argparse.ArgumentParser(description=__doc__)

    # output directory
    parser.add_argument('inputdir', type=str,
                        help='Input Melodic Directory')

    parser.add_argument('-o', '--outputdir', type=str, default='tfm.ica',
                        help='Directory where results will be stored. Def: tfm.ica')

    parser.add_argument('-l', '--labelfile', type=str,
                        default='hand_classification.txt',
                        help='Name of classification file. Default hand_classification.txt')

    parser.add_argument('--n_components', type=int, default=None,
                        help='Number of components to extract from tICA decomposition')

    parser.add_argument('--tolerance', type=float, default=1e-4,
                        help='ICA tolerance. Default 1e-4')

    parser.add_argument('--max_iter', type=int, default=10_000,
                        help='ICA max number of iterations')

    parser.add_argument('--dryrun', action='store_true',
                        help='Print which files would be generated.')

    return parser


if __name__ == '__main__':
    run_tfm()