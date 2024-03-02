import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import base64
import requests

FIG_SIZE = (10, 6)


def get_requests_response(url_template, **kwargs):
    response = requests.get(url_template.format(**kwargs))
    response_json = response.json()
    return response_json


def jaccard_sim(df):
    columns = df.columns
    jaccard_matrix = np.empty([len(columns), len(columns)])
    for i, row in enumerate(columns):
        for j, col in enumerate(columns):
            jaccard_sim = len(set(df[row]).intersection(set(df[col]))) / len(
                set(df[row]).union(set(df[col]))
            )
            jaccard_matrix[i, j] = jaccard_sim
    jaccard_sim_df = pd.DataFrame(index=columns, columns=columns, data=jaccard_matrix)
    return jaccard_sim_df


def get_img_as_base64(file):
    with open(file, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()


def human_readable(num):
    if num > 1000000:
        if not num % 1000000:
            return f"{num // 1000000}M"
        return f"{round(num / 1000000, 1)}M"
    return f"{num // 1000}K"


class word_list_venn_diagram(object):

    def __init__(self, words, fontsizes, polarities, colour1="#46A0F8", colour2="#FF2E63", alpha1=1.0, alpha2=1.0, scale=1.0):
        """
        Arguments:
        ----------
            words: [str 1, ... str N]
                list of strings
            fontsizes: [float 1, ... float N]
                corresponding list of (relative) fontsizes
            polarity: [-1, 0, 1, ..., 0, 1]
                corresponding list of area designations;
                polarity of 0 corresponds to intersection;
                polarities -1 and 1 correspond to the disjoint sets
            scale: float
                scales the size of the circles with respect to the text
                (w.r.t. the maximum joint height of the bounding boxes of the 3 word lists)

        Returns:
        --------
            None

        """

        self.words = np.array(words)
        self.fontsizes = np.array(fontsizes)
        self.colour1 = str(colour1)
        self.colour2 = str(colour2)
        self.alpha1 = float(alpha1)
        self.alpha2 = float(alpha2)

        # get bounding boxes of text
        self.bboxes = [
            self._get_bbox(word, size) for word, size in zip(self.words, self.fontsizes)
        ]

        # determine minimum radius of circles
        diameter = 0.0
        unique_polarities = np.unique(polarities)
        for polarity in unique_polarities:
            (idx,) = np.where(polarities == polarity)
            heights = [self.bboxes[ii].height for ii in idx]
            total = np.sum(heights)
            if total > diameter:
                diameter = total
        radius = diameter / 2.0

        # rescale
        radius *= scale
        self.radius = radius

        # arrange bboxes vertically
        for polarity in unique_polarities:
            (idx,) = np.where(polarities == polarity)
            order = self._argsort(self.fontsizes[idx])
            heights = [self.bboxes[ii].height for ii in idx]
            total = np.sum(heights)

            current_height = 0.0
            for ii in idx[order]:
                self.bboxes[ii].y = current_height - total / 2.0
                current_height += self.bboxes[ii].height

        # arrange bboxes horizontally
        # NB: slightly cheeky use of polarity argument
        for ii, _ in enumerate(self.bboxes):
            self.bboxes[ii].x = polarities[ii] * self._get_shift(  # type: ignore
                self.bboxes[ii].y, self.radius  # type: ignore
            )

        # draw
        self.fig, self.ax = self.draw()

        return

    def draw(self):
        """
        Draws the Venn diagram.
        """

        fig, ax = plt.subplots(1, 1, figsize=FIG_SIZE)

        # draw circles
        circle_left = plt.Circle(  # type: ignore
            (-0.5 * self.radius, 0),
            self.radius,
            alpha=self.alpha1,
            color=self.colour1,
            fill=False,
            axes=ax,
            linewidth=5,
        )
        circle_right = plt.Circle(  # type: ignore
            (+0.5 * self.radius, 0),
            self.radius,
            alpha=self.alpha2,
            color=self.colour2,
            fill=False,
            axes=ax,
            linewidth=5,
        )
        ax.add_artist(circle_left)
        ax.add_artist(circle_right)

        # draw words
        for ii, (word, bb, fs) in enumerate(
            zip(self.words, self.bboxes, self.fontsizes)
        ):
            ax.text(
                bb.x,  # type: ignore
                bb.y,  # type: ignore
                word,
                horizontalalignment="center",
                verticalalignment="center",
                fontsize=fs,
                fontfamily="monospace",
                bbox=dict(pad=0.0, facecolor="none", edgecolor="none"),
            )

        # update data limits as circles are not registered automatically
        corners = (-1.5 * self.radius, -self.radius), (1.5 * self.radius, self.radius)
        ax.update_datalim(corners)
        ax.autoscale_view()

        # make figure pretty-ish
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        ax.get_figure().set_facecolor("#F5F5F5")
        ax.set_frame_on(False)
        ax.get_figure().canvas.draw()

        return fig, ax

    def _get_bbox(self, word, fontsize):
        """
        Get the bounding box for each word.
        Unfortunately, the bbox is dependent on the renderer,
        so a figure has to be created.
        """
        fig = plt.figure(figsize=FIG_SIZE)
        renderer = fig.canvas.get_renderer()  # type: ignore
        text = plt.text(
            0.5,
            0.5,
            word,
            fontsize=fontsize,
            bbox=dict(pad=0.0, facecolor="none", edgecolor="red"),
        )
        bbox = text.get_window_extent(renderer=renderer)
        plt.close(fig)
        return bbox

    def _argsort(self, arr):
        """
        Returns indices to create a sorted array.
        Entries are sorted in such a way that the largest element is in the middle,
        and the size of the elements falls off towards the ends.
        """
        order = np.argsort(arr)
        order = np.r_[order[::2], order[1::2][::-1]]
        return order

    def _get_shift(self, y, r):
        """
        Get point along midline of a waxing moon formed by two overlapping
        circles of radius r as a function of y.
        """
        x1 = np.sqrt(r**2 - y**2) + r / 2.0  # right circle
        x2 = np.sqrt(r**2 - y**2) - r / 2.0  # left circle
        x = x2 + (x1 - x2) / 2.0  # midpoint
        return x
